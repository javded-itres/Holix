"""Telegram confirmation / plan-review UI cleanup."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.security.confirmation import ConfirmationChoice, init_action_guard
from integrations.telegram.approvals import (
    TelegramApprovals,
    _callback_data,
    _register_callback_token,
)
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


def test_register_callback_token_keeps_siblings() -> None:
    mapping: dict[str, str] = {}
    a = _register_callback_token(mapping, "confirm_a")
    b = _register_callback_token(mapping, "confirm_b")
    assert a != b
    assert mapping[a] == "confirm_a"
    assert mapping[b] == "confirm_b"


def test_resolve_one_confirmation_keeps_sibling_token(
    approvals: TelegramApprovals, session: ChatSession
) -> None:
    agent = MagicMock()
    agent.tools = MagicMock()
    agent.subagents = None
    bus = MagicMock()
    guard = init_action_guard(event_bus=bus, confirmation_timeout=0)
    agent.tools._action_guard = guard
    session.agent = agent

    loop = asyncio.new_event_loop()
    try:
        fa = loop.create_future()
        fb = loop.create_future()
        guard._pending_confirmations["confirm_a"] = fa
        guard._pending_confirmations["confirm_b"] = fb
        ta = _register_callback_token(session.approval_callback_tokens, "confirm_a")
        tb = _register_callback_token(session.approval_callback_tokens, "confirm_b")
        assert approvals.resolve_confirmation_callback(ta, "1") is True
        assert fa.result() == ConfirmationChoice.ALLOW_ONCE
        assert not fb.done()
        assert session.approval_callback_tokens[tb] == "confirm_b"
        assert ta not in session.approval_callback_tokens
    finally:
        loop.close()


def test_callback_data_stays_within_telegram_limit() -> None:
    token = _register_callback_token({}, "confirm_99_" + "x" * 80)
    assert len(_callback_data("cfm", token, "1").encode("utf-8")) <= 64


def test_resolve_confirmation_via_short_token(
    approvals: TelegramApprovals, session: ChatSession
) -> None:
    agent = MagicMock()
    agent.tools = MagicMock()
    agent.subagents = None
    bus = MagicMock()
    guard = init_action_guard(event_bus=bus, confirmation_timeout=0)
    agent.tools._action_guard = guard
    session.agent = agent

    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        guard._pending_confirmations["confirm_1_tg_default_100"] = future
        token = _register_callback_token(
            session.approval_callback_tokens,
            "confirm_1_tg_default_100",
        )
        assert approvals.resolve_confirmation_callback(token, "1") is True
        assert future.result() == ConfirmationChoice.ALLOW_ONCE
    finally:
        loop.close()


def test_resolve_confirmation_fallback_to_latest_pending(
    approvals: TelegramApprovals, session: ChatSession
) -> None:
    agent = MagicMock()
    agent.tools = MagicMock()
    agent.subagents = None
    bus = MagicMock()
    guard = init_action_guard(event_bus=bus, confirmation_timeout=0)
    agent.tools._action_guard = guard
    session.agent = agent

    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        guard._pending_confirmations["confirm_2_tg_default_100"] = future
        # Wrong/stale id from an old inline keyboard — should still resolve latest.
        assert approvals.resolve_confirmation_callback("stale_token", "2") is True
        assert future.result() == ConfirmationChoice.ALLOW_SESSION
    finally:
        loop.close()
