"""MAX confirmation / plan-review UI cleanup."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.security.confirmation import ConfirmationChoice, init_action_guard
from integrations.max.approvals import (
    MaxApprovals,
    _register_callback_token,
)
from integrations.max.session import MaxChatSession


@pytest.fixture
def session() -> MaxChatSession:
    return MaxChatSession(
        user_id=1,
        profile="default",
        conversation_id="max_default_1",
    )


@pytest.fixture
def approvals(session: MaxChatSession) -> MaxApprovals:
    client = AsyncMock()
    return MaxApprovals(client, session)


@pytest.mark.asyncio
async def test_dismiss_confirmation_deletes_stored_message(
    approvals: MaxApprovals, session: MaxChatSession
) -> None:
    session.pending_confirmation_message_id = "mid-42"
    await approvals.dismiss_confirmation_ui()
    approvals._client.delete_message.assert_awaited_once_with("mid-42")
    assert session.pending_confirmation_message_id is None


@pytest.mark.asyncio
async def test_dismiss_plan_review_deletes_all_stored_messages(
    approvals: MaxApprovals, session: MaxChatSession
) -> None:
    session.pending_plan_message_ids = ["mid-10", "mid-11"]
    await approvals.dismiss_plan_review_ui()
    assert approvals._client.delete_message.await_count == 2
    approvals._client.delete_message.assert_any_await("mid-10")
    approvals._client.delete_message.assert_any_await("mid-11")
    assert session.pending_plan_message_ids == []


@pytest.mark.asyncio
async def test_dismiss_confirmation_ignores_delete_errors(
    approvals: MaxApprovals, session: MaxChatSession
) -> None:
    session.pending_confirmation_message_id = "mid-99"
    approvals._client.delete_message.side_effect = Exception("already gone")
    await approvals.dismiss_confirmation_ui()
    assert session.pending_confirmation_message_id is None


def test_resolve_confirmation_via_short_token(
    approvals: MaxApprovals, session: MaxChatSession
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
        guard._pending_confirmations["confirm_1_max_default_1"] = future
        token = _register_callback_token(
            session.approval_callback_tokens,
            "confirm_1_max_default_1",
        )
        assert approvals.resolve_confirmation_callback(token, "1") is True
        assert future.result() == ConfirmationChoice.ALLOW_ONCE
    finally:
        loop.close()


def test_resolve_confirmation_fallback_to_latest_pending(
    approvals: MaxApprovals, session: MaxChatSession
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
        guard._pending_confirmations["confirm_2_max_default_1"] = future
        assert approvals.resolve_confirmation_callback("stale_token", "2") is True
        assert future.result() == ConfirmationChoice.ALLOW_SESSION
    finally:
        loop.close()