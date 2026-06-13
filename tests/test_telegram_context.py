"""Telegram context compression events and session integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from core.agent_events import ContextCompressedEvent, ContextWarningEvent
from integrations.telegram.event_handler import TelegramEventHandler


def _handler_with_buffer() -> tuple[TelegramEventHandler, MagicMock]:
    presenter = MagicMock()
    buf = MagicMock()
    presenter.buffer = buf
    presenter.session = MagicMock()
    presenter.schedule_edit = MagicMock()
    handler = TelegramEventHandler(presenter, approvals=MagicMock())
    return handler, buf


def test_telegram_handler_shows_context_compressed_event() -> None:
    handler, buf = _handler_with_buffer()
    handler.handle(
        ContextCompressedEvent(
            original_tokens=90_000,
            compressed_tokens=12_000,
            messages_before=40,
            messages_after=11,
            summary_preview="User asked about deployment",
        )
    )
    assert buf.add_note.call_count >= 1
    first = buf.add_note.call_args_list[0].args[0]
    assert "Context compressed" in first
    assert "90,000" in first
    assert "12,000" in first


def test_telegram_handler_shows_context_warning_event() -> None:
    handler, buf = _handler_with_buffer()
    handler.handle(
        ContextWarningEvent(
            usage_percent=72.5,
            tokens_used=72_500,
            tokens_total=100_000,
            level="warning",
        )
    )
    note = buf.add_note.call_args.args[0]
    assert "72%" in note
    assert "72,500" in note


def test_telegram_handler_shows_critical_context_warning() -> None:
    handler, buf = _handler_with_buffer()
    handler.handle(
        ContextWarningEvent(
            usage_percent=91.0,
            tokens_used=91_000,
            tokens_total=100_000,
            level="critical",
        )
    )
    note = buf.add_note.call_args.args[0]
    assert "compressing" in note


@pytest.mark.asyncio
async def test_prepare_session_auto_compress_persists_for_telegram_conversation(
    memory_manager,
) -> None:
    """Telegram uses the same prepare_session path as TUI (per conversation_id)."""
    from core.agent_events import AgentEventBus
    from core.context import ContextCompressor, ContextManager, TokenCounter
    from core.runtime.session import prepare_session

    agent = type("Agent", (), {})()
    agent.memory = memory_manager
    agent.events = AgentEventBus(name="test")
    agent.context_manager = ContextManager(
        context_window=200,
        token_counter=TokenCounter(),
        compressor=ContextCompressor(
            client=AsyncMock(),
            model="test-model",
            token_counter=TokenCounter(),
        ),
        event_bus=agent.events,
        compression_threshold=0.5,
        warning_threshold=0.3,
    )
    agent.context_manager.compressor.compress = AsyncMock(
        return_value=(
            [{"role": "system", "content": "summary"}, {"role": "user", "content": "latest"}],
            "compressed summary",
        )
    )

    conversation_id = "tg_default_12345"
    for i in range(15):
        await agent.memory.save_message(conversation_id, "user", f"message {i} " + ("x" * 80))

    messages, was_compressed = await prepare_session(agent, "new question", conversation_id)
    assert was_compressed is True
    assert len(messages) == 3
    assert messages[0]["metadata"]["type"] == "agent_soul"
    stored = await agent.memory.get_conversation(conversation_id)
    assert any("summary" in (m.get("content") or "") for m in stored)