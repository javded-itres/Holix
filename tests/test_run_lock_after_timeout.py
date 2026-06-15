"""Messenger run_lock must be released after an aborted agent run."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.agent_events import FinalResponseEvent
from integrations.telegram.session import ChatSession


@pytest.mark.asyncio
async def test_telegram_run_lock_released_after_timeout_final() -> None:
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
    bot.edit_message_text = AsyncMock()

    session = ChatSession(chat_id=1, user_id=1, profile="default", conversation_id="tg_default_1")
    agent = MagicMock()
    agent.model = "slow"
    session.agent = agent

    from integrations.telegram.host import TelegramHost

    host = TelegramHost(bot, session)

    async def fake_consume(*_args, emit, **_kwargs):
        emit(
            FinalResponseEvent(
                content="Модель не ответила за 120 с. Попробуйте ещё раз.",
                steps_taken=1,
                conversation_id=session.conversation_id,
            )
        )

    class _Events:
        def __init__(self) -> None:
            self._handlers: list = []

        def subscribe(self, handler) -> None:
            self._handlers.append(handler)

        def unsubscribe(self, handler) -> None:
            self._handlers.remove(handler)

    agent.events = _Events()

    with (
        patch("integrations.telegram.host.TelegramLivePresenter") as presenter_cls,
        patch("integrations.telegram.event_handler.TelegramEventHandler"),
        patch("integrations.telegram.approvals.TelegramApprovals"),
        patch("core.session_models.ensure_session_model"),
        patch("core.runtime.run_consumer.consume_run_holix", side_effect=fake_consume),
        patch("core.tools.execution_context.chat_delivery_scope", return_value="token"),
        patch("core.tools.execution_context.reset_chat_delivery_scope"),
        patch("core.workspace.agent_path_visibility_context") as vis_ctx,
        patch("integrations.telegram.access_approval.is_telegram_admin", return_value=False),
    ):
        vis_ctx.return_value.__enter__ = MagicMock(return_value=None)
        vis_ctx.return_value.__exit__ = MagicMock(return_value=False)

        class FakePresenter:
            final_delivered = True

            async def start(self) -> None:
                return None

            async def finish(self) -> None:
                return None

            def schedule_edit(self, *, force: bool = False) -> None:
                return None

            def note_final_content(self, content: str) -> None:
                return None

            def enqueue_outbound(self, coro) -> None:
                return None

            @property
            def buffer(self):
                return session.live_buffer

        presenter_cls.side_effect = lambda *a, **k: FakePresenter()

        session.streaming_enabled = True
        await host._run_agent("first message")
        assert not session.run_lock.locked()

        second_started = asyncio.Event()

        async def mark_second() -> None:
            second_started.set()

        original_locked = host._run_agent_locked

        async def wrapped_locked(user_input: str) -> None:
            second_started.set()
            await original_locked(user_input)

        host._run_agent_locked = wrapped_locked  # type: ignore[method-assign]
        host._start_agent_run("second message")
        await asyncio.wait_for(second_started.wait(), timeout=1.0)