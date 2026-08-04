"""Background process notices are pinned (Telegram) / best-effort pin (MAX)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from core.agent_events import BackgroundProcessStartedEvent, BackgroundProcessStoppedEvent
from integrations.telegram.event_handler import TelegramEventHandler
from integrations.telegram.session import ChatSession


@pytest.mark.asyncio
async def test_telegram_pins_background_process_notice() -> None:
    session = ChatSession(
        chat_id=42,
        user_id=7,
        profile="admin",
        conversation_id="tg_admin_1",
    )
    from core.presenters.live_buffer import LiveTranscriptBuffer

    session.live_buffer = LiveTranscriptBuffer(profile="admin", mode="react")
    session.live_buffer.publish_answer_separately = True

    bot = MagicMock()
    sent = MagicMock()
    sent.message_id = 9001
    bot.send_message = AsyncMock(return_value=sent)
    bot.pin_chat_message = AsyncMock()
    bot.unpin_chat_message = AsyncMock()
    bot.edit_message_text = AsyncMock()

    from integrations.telegram.live_presenter import TelegramLivePresenter

    presenter = TelegramLivePresenter(bot, session)
    presenter._outbound_queue = __import__("asyncio").Queue()
    presenter._outbound_worker = None
    # Drain queue manually after handle
    handler = TelegramEventHandler(presenter, approvals=MagicMock())

    handler.handle(
        BackgroundProcessStartedEvent(
            process_id="proc_abc",
            label="telegram_channel_publisher",
            pid=12345,
            conversation_id=session.conversation_id,
        )
    )
    # Run outbound job
    job = presenter._outbound_queue.get_nowait()
    await job

    bot.send_message.assert_awaited()
    bot.pin_chat_message.assert_awaited()
    pin_kwargs = bot.pin_chat_message.await_args
    assert pin_kwargs.args[0] == 42 or pin_kwargs.kwargs.get("chat_id") == 42
    assert session.background_process_message_ids.get("proc_abc") == 9001

    handler.handle(
        BackgroundProcessStoppedEvent(
            process_id="proc_abc",
            label="telegram_channel_publisher",
            conversation_id=session.conversation_id,
        )
    )
    job2 = presenter._outbound_queue.get_nowait()
    await job2
    bot.unpin_chat_message.assert_awaited()
    assert "proc_abc" not in session.background_process_message_ids


@pytest.mark.asyncio
async def test_max_client_pin_endpoints() -> None:
    from integrations.max.client import MaxClient

    client = MaxClient(access_token="tok", base_url="https://example.test")
    client._request = AsyncMock(return_value={"success": True})
    await client.pin_message(1001, "mid-xyz", notify=False)
    client._request.assert_awaited()
    args = client._request.await_args
    assert args.args[0] == "PUT"
    assert "/chats/1001/pin" in args.args[1]
    await client.unpin_message(1001)
    assert client._request.await_args.args[0] == "DELETE"
