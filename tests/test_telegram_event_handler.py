"""Telegram agent event → message delivery."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.agent_events import FinalResponseEvent
from core.presenters.live_buffer import LiveTranscriptBuffer
from integrations.telegram.event_handler import TelegramEventHandler
from integrations.telegram.session import ChatSession


@pytest.fixture
def handler_setup() -> tuple[TelegramEventHandler, MagicMock, ChatSession]:
    session = ChatSession(
        chat_id=1,
        user_id=2,
        profile="docs",
        conversation_id="tg_docs_1",
    )
    session.live_buffer = LiveTranscriptBuffer(profile="docs", mode="react")
    session.live_buffer.publish_answer_separately = True

    presenter = MagicMock()
    presenter.session = session
    presenter.buffer = session.live_buffer
    presenter.deliver_result = AsyncMock()

    approvals = MagicMock()
    handler = TelegramEventHandler(presenter, approvals)
    return handler, presenter, session


@pytest.mark.asyncio
async def test_final_response_always_delivered_separately(
    handler_setup: tuple[TelegramEventHandler, MagicMock, ChatSession],
) -> None:
    handler, presenter, session = handler_setup
    handler.handle(FinalResponseEvent(content="## Итог\n\nВсё готово."))
    await asyncio.sleep(0)

    presenter.deliver_result.assert_called_once_with("## Итог\n\nВсё готово.")
    assert session.live_buffer.answer == ""
    assert session.live_buffer.result_posted_separately is True
    assert session.live_buffer.status == "done"


@pytest.mark.asyncio
async def test_final_response_falls_back_to_last_tool_result(
    handler_setup: tuple[TelegramEventHandler, MagicMock, ChatSession],
) -> None:
    handler, presenter, session = handler_setup
    session._recent_tool_results.append(
        {"name": "run_terminal_command", "full_result": "command output line"}
    )

    handler.handle(FinalResponseEvent(content=""))
    await asyncio.sleep(0)

    presenter.deliver_result.assert_called_once_with("command output line")
    assert session.live_buffer.status == "done"