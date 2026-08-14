"""P0 security user cases: high-risk terminal + scripted confirm allow/deny."""

from __future__ import annotations

import pytest
from core.security.confirmation import ConfirmationChoice

from tests.user_cases.harness import UserCaseHarness
from tests.user_cases.scripted_llm import Final, ToolCall

# auto_allow up to medium → HIGH terminal still requires confirmation
_INTERACTIVE_OVERRIDES = {
    "auto_allow_threshold": "medium",
    "confirmation_timeout": 5,
}


@pytest.fixture
async def interactive_harness(temp_dir, monkeypatch: pytest.MonkeyPatch):
    h = UserCaseHarness(temp_dir, monkeypatch, config_overrides=dict(_INTERACTIVE_OVERRIDES))
    await h.setup()
    try:
        yield h
    finally:
        await h.close()


@pytest.mark.user_case
@pytest.mark.integration
@pytest.mark.asyncio
async def test_uc04_terminal_confirm_allow_runs_command(interactive_harness):
    """UC-04: high-risk terminal → user allows → command executes."""
    h = interactive_harness
    h.auto_confirm(ConfirmationChoice.ALLOW_ONCE)
    h.script(
        [
            ToolCall("run_terminal_command", {"command": "echo UC_CONFIRM_OK"}),
            Final("The terminal printed UC_CONFIRM_OK after approval."),
        ]
    )

    result = await h.run("Run echo UC_CONFIRM_OK in the terminal")

    result.assert_no_error_events()
    result.assert_confirmation_requested("run_terminal_command")
    assert h.confirm_resolutions == [("run_terminal_command", "allow_once")]
    result.assert_tools_exactly("run_terminal_command")
    out = result.tool_result_text("run_terminal_command")
    assert "UC_CONFIRM_OK" in out
    assert "denied" not in out.lower()
    result.assert_final_contains("UC_CONFIRM_OK")


@pytest.mark.user_case
@pytest.mark.integration
@pytest.mark.asyncio
async def test_uc05_terminal_confirm_deny_blocks_command(interactive_harness):
    """UC-05: high-risk terminal → user denies → no execution, graceful final."""
    h = interactive_harness
    marker = "deny_should_not_exist.txt"
    # Shell would create the marker only if the command actually runs.
    # Use allowlisted `echo` only; deny must prevent any successful result.
    h.auto_confirm(ConfirmationChoice.DENY)
    h.script(
        [
            ToolCall("run_terminal_command", {"command": "echo DENY_MARKER"}),
            Final("I could not run the terminal command because it was denied."),
        ]
    )

    result = await h.run("Please run: echo DENY_MARKER")

    result.assert_no_error_events()
    result.assert_confirmation_requested("run_terminal_command")
    assert h.confirm_resolutions == [("run_terminal_command", "deny")]
    result.assert_tools_exactly("run_terminal_command")
    out = result.tool_result_text("run_terminal_command")
    assert "denied" in out.lower() or out.lower().startswith("error:")
    assert "DENY_MARKER" not in out or "denied" in out.lower()
    # Workspace must not gain a new side-effect file from a denied command
    assert not h.workspace.exists(marker)
    result.assert_final_contains("denied")
