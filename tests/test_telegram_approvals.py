"""Telegram confirmation / plan-review UI cleanup."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from integrations.telegram.approvals import TelegramApprovals
from integrations.telegram.session import ChatSession


@pytest.fixture
def session() -> ChatSession:
    return ChatSession(
        chat_id=100,
        user_id=1,
        profile="default",
        conversation_id="tg_default_100",
    )


@pytest.fixture
def approvals(session: ChatSession) -> TelegramApprovals:
    bot = AsyncMock()
    return TelegramApprovals(bot, session)


@pytest.mark.asyncio
async def test_dismiss_confirmation_deletes_stored_message(
    approvals: TelegramApprovals, session: ChatSession
) -> None:
    session.pending_confirmation_message_id = 42
    await approvals.dismiss_confirmation_ui()
    approvals._bot.delete_message.assert_awaited_once_with(100, 42)
    assert session.pending_confirmation_message_id is None


@pytest.mark.asyncio
async def test_dismiss_plan_review_deletes_all_stored_messages(
    approvals: TelegramApprovals, session: ChatSession
) -> None:
    session.pending_plan_message_ids = [10, 11]
    await approvals.dismiss_plan_review_ui()
    assert approvals._bot.delete_message.await_count == 2
    approvals._bot.delete_message.assert_any_await(100, 10)
    approvals._bot.delete_message.assert_any_await(100, 11)
    assert session.pending_plan_message_ids == []


@pytest.mark.asyncio
async def test_dismiss_confirmation_ignores_delete_errors(
    approvals: TelegramApprovals, session: ChatSession
) -> None:
    session.pending_confirmation_message_id = 99
    approvals._bot.delete_message.side_effect = Exception("already gone")
    await approvals.dismiss_confirmation_ui()
    assert session.pending_confirmation_message_id is None