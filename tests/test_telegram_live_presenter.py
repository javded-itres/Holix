"""Telegram live presenter delivery guarantees."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from integrations.telegram.live_presenter import TelegramLivePresenter, _is_not_modified
from integrations.telegram.session import ChatSession


def test_is_not_modified_detects_telegram_error() -> None:
    assert _is_not_modified(Exception("Bad Request: message is not modified"))
    assert not _is_not_modified(Exception("network down"))


@pytest.mark.asyncio
async def test_do_edit_fallback_keeps_html_working_indicator() -> None:
    bot = MagicMock()
    bot.edit_message_text = AsyncMock(side_effect=Exception("parse error"))
    session = ChatSession(chat_id=1, user_id=2, profile="default", conversation_id="tg_default_1")
    session.bump_live_buffer()
    session.live_message_id = 42
    presenter = TelegramLivePresenter(bot, session)

    await presenter._do_edit()

    assert bot.edit_message_text.await_count == 2
    fallback = bot.edit_message_text.await_args_list[1].args[0]
    assert fallback == "<i>⏳ Working…</i>"
    assert "&lt;i&gt;" not in fallback


@pytest.mark.asyncio
async def test_do_edit_ignores_not_modified() -> None:
    bot = MagicMock()
    bot.edit_message_text = AsyncMock(
        side_effect=Exception("Bad Request: message is not modified")
    )
    session = ChatSession(chat_id=1, user_id=2, profile="default", conversation_id="tg_default_1")
    session.bump_live_buffer()
    session.live_message_id = 42
    presenter = TelegramLivePresenter(bot, session)

    await presenter._do_edit()

    bot.edit_message_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_finish_delivers_full_content_not_preview_placeholder() -> None:
    bot = MagicMock()
    bot.edit_message_text = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=99))
    session = ChatSession(chat_id=1, user_id=2, profile="default", conversation_id="tg_default_1")
    session.bump_live_buffer()
    session.live_message_id = 42
    session.live_buffer.set_answer("✓ Done — full answer below.")
    session.live_buffer.mark_done()

    presenter = TelegramLivePresenter(bot, session)
    presenter.note_final_content("This is the real final answer from the agent.")
    await presenter.finish()

    assert bot.send_message.await_count == 1
    sent = bot.send_message.await_args_list[0].args[1]
    assert "real final answer" in sent
    assert presenter.final_delivered is True


@pytest.mark.asyncio
async def test_deliver_final_answer_only_once() -> None:
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=99))
    session = ChatSession(chat_id=1, user_id=2, profile="default", conversation_id="tg_default_1")
    presenter = TelegramLivePresenter(bot, session)

    await presenter.deliver_final_answer("**hello** world")
    await presenter.deliver_final_answer("**hello** world")

    assert bot.send_message.await_count == 1
    sent = bot.send_message.await_args_list[0].args[1]
    assert "<b>hello</b>" in sent