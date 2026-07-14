"""Tests for /forget session memory wipe."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cli.shared.commands.forget_memory import (
    run_forget_memory,
    wipe_conversation_memory_for_host,
)


@pytest.mark.asyncio
async def test_wipe_conversation_memory_for_host(memory_manager) -> None:
    conv_id = "studio_test"
    await memory_manager.save_message(conv_id, "user", "Remember the kubernetes plan")
    await memory_manager.save_message(conv_id, "assistant", "Plan saved")

    host = SimpleNamespace(
        conversation_id=conv_id,
        agent=SimpleNamespace(
            memory=memory_manager,
            context_manager=SimpleNamespace(
                invalidate_usage_cache=lambda _cid: None,
            ),
        ),
    )

    assert await wipe_conversation_memory_for_host(host) is True
    assert await memory_manager.get_conversation(conv_id, limit=10) == []


@pytest.mark.asyncio
async def test_run_forget_memory_clears_search_ui(memory_manager) -> None:
    conv_id = "forget-ui"
    await memory_manager.save_message(conv_id, "user", "hello world test message")

    messages: list[str] = []

    host = SimpleNamespace(
        conversation_id=conv_id,
        agent=SimpleNamespace(
            memory=memory_manager,
            context_manager=None,
        ),
        _memory_search_query="old query",
        _memory_search_results=[{"x": 1}],
        transcript_write=messages.append,
        profile="default",
    )

    await run_forget_memory(host, clear_ui=False)

    assert host._memory_search_query == ""
    assert host._memory_search_results == []
    assert await memory_manager.get_conversation(conv_id, limit=5) == []
    assert messages and "cleared" in messages[-1].lower() or "очищ" in messages[-1].lower()