"""Shared /compress slash command."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from cli.shared.commands.context_compress import run_context_compress
from cli.shared.commands.registry import SLASH_COMMANDS


def test_compress_in_slash_registry():
    cmds = {c for c, _ in SLASH_COMMANDS}
    assert "/compress" in cmds


@pytest.mark.asyncio
async def test_run_context_compress_success():
    messages = [{"role": "user", "content": "a"}] * 5
    compressed = [{"role": "system", "content": "summary"}, {"role": "user", "content": "a"}]

    mock_agent = MagicMock()
    mock_agent.context_manager.compressor = MagicMock()
    mock_agent.memory.get_conversation = AsyncMock(return_value=messages)
    mock_agent.memory.replace_conversation_messages = AsyncMock()
    mock_agent.token_counter.count_message_tokens.side_effect = [1000, 200]
    mock_agent.context_manager.compress_context = AsyncMock(return_value=(compressed, True))
    mock_agent.context_manager.last_summary = "summary text"

    lines: list[str] = []

    class Host:
        agent = mock_agent
        conversation_id = "conv-1"

        @staticmethod
        def transcript_write(content: object) -> None:
            lines.append(str(content))

    await run_context_compress(Host())

    assert any("compressed" in line.lower() for line in lines)
    mock_agent.memory.replace_conversation_messages.assert_awaited_once_with(
        "conv-1", compressed
    )


@pytest.mark.asyncio
async def test_run_context_compress_no_agent():
    lines: list[str] = []

    class Host:
        agent = None
        conversation_id = "x"

        @staticmethod
        def transcript_write(content: object) -> None:
            lines.append(str(content))

    await run_context_compress(Host())
    assert any("not ready" in line.lower() for line in lines)