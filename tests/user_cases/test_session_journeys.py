"""P1 session journeys: multi-turn memory and max_steps budget."""

from __future__ import annotations

import pytest

from tests.user_cases.harness import UserCaseHarness
from tests.user_cases.scripted_llm import Final, ToolCall


@pytest.mark.user_case
@pytest.mark.integration
@pytest.mark.asyncio
async def test_uc13_multi_turn_conversation_memory(harness):
    """UC-13: same conversation_id keeps user/assistant history across runs."""
    harness.script([Final("Got it, the secret code is ALPHA42.")])
    r1 = await harness.run(
        "Remember the secret code is ALPHA42.",
        conversation_id="uc13_mem",
    )
    r1.assert_no_error_events()
    r1.assert_final_contains("ALPHA42")

    harness.script([Final("The secret code is ALPHA42.")])
    r2 = await harness.run(
        "What is the secret code?",
        conversation_id="uc13_mem",
    )
    r2.assert_no_error_events()
    r2.assert_final_contains("ALPHA42")

    assert harness.agent is not None
    hist = await harness.agent.memory.get_conversation("uc13_mem", limit=20)
    roles = [m.get("role") for m in hist]
    contents = " ".join(str(m.get("content") or "") for m in hist)
    assert roles.count("user") >= 2
    assert roles.count("assistant") >= 2
    assert "ALPHA42" in contents
    assert "What is the secret code?" in contents


@pytest.mark.user_case
@pytest.mark.integration
@pytest.mark.asyncio
async def test_uc14_max_steps_stops_without_hang(temp_dir, monkeypatch: pytest.MonkeyPatch):
    """UC-14: low max_steps + tool loop emits MaxStepsReached and finishes."""
    h = UserCaseHarness(
        temp_dir,
        monkeypatch,
        config_overrides={
            "max_steps": 2,
            "max_steps_extend_enabled": False,
        },
    )
    await h.setup()
    try:
        h.workspace.write("a.txt", "payload")
        # Two tool-request turns exhaust the budget; leftover Final is unused.
        h.script(
            [
                ToolCall("read_file", {"path": "a.txt"}),
                ToolCall("read_file", {"path": "a.txt"}),
                Final("should not be required"),
            ]
        )

        result = await h.run(
            "Keep reading a.txt",
            conversation_id="uc14_max",
            expect_exhausted=False,
        )

        result.assert_no_error_events()
        result.assert_max_steps_reached()
        # At least the first tool completed under the budget
        assert "read_file" in result.tool_names
        assert h.llm.remaining <= 1
    finally:
        await h.close()
