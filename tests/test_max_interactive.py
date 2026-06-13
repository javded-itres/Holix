"""MAX interactive keyboards and callback tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from integrations.max.keyboards import (
    confirmation_keyboard,
    mode_picker_keyboard,
    parse_callback,
    plan_review_keyboard,
)
from integrations.max.models import (
    callback_id_from_update,
    callback_payload_from_update,
    callback_reply_target,
)
from integrations.max.session import MaxChatSession


def test_parse_callback_hx_prefix() -> None:
    assert parse_callback("hx:m:react") == ("m", "react")
    assert parse_callback("cfm:abc:1") is None


def test_inline_keyboard_shape() -> None:
    kb = mode_picker_keyboard(["react", "auto"], "react")
    assert kb["type"] == "inline_keyboard"
    buttons = kb["payload"]["buttons"]
    assert buttons[0][0]["type"] == "callback"
    assert buttons[0][0]["payload"].startswith("hx:m:")


def test_confirmation_keyboard_payload() -> None:
    kb = confirmation_keyboard("cid-99")
    btn = kb["payload"]["buttons"][0][0]
    assert btn["payload"] == "cfm:cid-99:1"


def test_plan_review_keyboard_payload() -> None:
    kb = plan_review_keyboard("rid-1")
    assert kb["payload"]["buttons"][0][0]["payload"] == "plan:rid-1:confirm"


def test_callback_update_helpers() -> None:
    update = {
        "update_type": "message_callback",
        "callback": {
            "callback_id": "cb-42",
            "payload": "hx:st:1",
            "user": {"user_id": 7},
            "message": {"recipient": {"user_id": 7}},
        },
    }
    assert callback_id_from_update(update) == "cb-42"
    assert callback_payload_from_update(update) == "hx:st:1"
    assert callback_reply_target(update) == (7, None)


@pytest.mark.asyncio
async def test_bot_handles_message_callback() -> None:
    from integrations.max.bot import HelixMaxBot
    from integrations.max.config import MaxSettings

    settings = MaxSettings(
        access_token="tok",
        allowed_user_ids="7",
        allow_all=False,
        profile="default",
    )
    bot = HelixMaxBot(settings)

    client = AsyncMock()
    client.answer_callback = AsyncMock(return_value={"success": True})

    update = {
        "update_type": "message_callback",
        "callback": {
            "callback_id": "cb-1",
            "payload": "hx:st:1",
            "user": {"user_id": 7},
            "message": {"recipient": {"user_id": 7}},
        },
    }

    await bot._handle_message_callback(client, update)
    client.answer_callback.assert_awaited_once()
    assert client.answer_callback.await_args.kwargs.get("notification") is not None


@pytest.mark.asyncio
async def test_max_approvals_sends_keyboard() -> None:
    from core.security.confirmation_events import ConfirmationRequestEvent
    from integrations.max.approvals import MaxApprovals

    session = MaxChatSession(user_id=7, profile="default", conversation_id="max_default_7")
    session.reply_user_id = 7
    client = AsyncMock()
    client.send_message = AsyncMock(return_value={"message": {"message_id": "m1"}})

    approvals = MaxApprovals(client, session)
    event = ConfirmationRequestEvent(
        confirmation_id="c1",
        tool_name="write_file",
        arguments={"path": "/tmp/x"},
        reason="write file",
        risk_level="high",
    )
    await approvals.on_confirmation_request(event)

    client.send_message.assert_awaited_once()
    kwargs = client.send_message.await_args.kwargs
    assert kwargs["attachments"]
    assert kwargs["attachments"][0]["type"] == "inline_keyboard"
    assert session.pending_confirmation_message_id == "m1"