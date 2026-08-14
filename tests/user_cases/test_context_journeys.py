"""P1 context compression journey inside agent.run."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.user_cases.scripted_llm import Final


@pytest.mark.user_case
@pytest.mark.integration
@pytest.mark.asyncio
async def test_uc12_context_compresses_during_run(harness):
    """UC-12: oversized history triggers ContextCompressedEvent before final answer."""
    assert harness.agent is not None
    agent = harness.agent
    cm = agent.context_manager
    cm.context_window = 400
    cm.compression_threshold = 0.2
    cm.system_prompt_reserve = 50
    cm.event_bus = agent.events

    async def _fake_compress(messages, keep_recent: int = 4):
        summary = "SUMMARY of long history"
        compressed = [
            {
                "role": "system",
                "content": f"Context compressed. Summary of previous conversation:\n\n{summary}",
            }
        ] + list(messages[-2:])
        return compressed, summary

    cm.compressor = MagicMock()
    cm.compressor.compress = AsyncMock(side_effect=_fake_compress)

    cid = "uc12_compress"
    filler_u = "User message with filler words " * 25
    filler_a = "Assistant reply with filler content " * 25
    for i in range(25):
        await agent.memory.save_message(cid, "user", f"{i}: {filler_u}")
        await agent.memory.save_message(cid, "assistant", f"{i}: {filler_a}")

    harness.script([Final("I see prior context was compressed. Ready to continue.")])
    result = await harness.run("Continue please", conversation_id=cid)

    result.assert_no_error_events()
    result.assert_context_compressed()
    result.assert_final_contains("compressed")
    assert cm.compressor.compress.await_count >= 1
