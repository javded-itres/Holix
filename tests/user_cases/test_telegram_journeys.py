"""P2 Telegram surface: confirmation callback path unblocks high-risk tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from integrations.telegram.approvals import TelegramApprovals, _register_callback_token
from integrations.telegram.session import ChatSession

from core.security.confirmation_events import ConfirmationRequestEvent
from tests.user_cases.harness import UserCaseHarness
from tests.user_cases.scripted_llm import Final, ToolCall

_INTERACTIVE = {
    "auto_allow_threshold": "medium",
    "confirmation_timeout": 5,
}


def _wire_telegram_confirm(
    *,
    agent,
    session: ChatSession,
    approvals: TelegramApprovals,
    code: str,
    resolved: list[str],
):
    """On ConfirmationRequestEvent: register TG callback token and resolve (sync).

    Uses the same token map + ``resolve_confirmation_callback`` as production
    keyboards, without requiring ``aiogram`` for markup construction.
    """

    def _on_event(event) -> None:
        if not isinstance(event, ConfirmationRequestEvent):
            return
        token = _register_callback_token(
            session.approval_callback_tokens,
            event.confirmation_id,
        )
        approvals._pending_confirm_id = event.confirmation_id
        ok = approvals.resolve_confirmation_callback(token, code)
        if ok:
            resolved.append(event.tool_name)

    agent.events.subscribe(_on_event)
    return _on_event


@pytest.mark.user_case
@pytest.mark.integration
@pytest.mark.asyncio
async def test_uc22_telegram_confirm_allow_runs_terminal(temp_dir, monkeypatch: pytest.MonkeyPatch):
    """UC-22: ConfirmationRequest → Telegram callback allow → terminal runs."""
    h = UserCaseHarness(temp_dir, monkeypatch, config_overrides=dict(_INTERACTIVE))
    await h.setup()
    assert h.agent is not None

    session = ChatSession(
        chat_id=4242,
        user_id=7,
        profile="default",
        conversation_id="uc22_tg",
    )
    session.agent = h.agent
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=9001))
    bot.delete_message = AsyncMock()
    approvals = TelegramApprovals(bot, session)
    resolved: list[str] = []
    handler = _wire_telegram_confirm(
        agent=h.agent,
        session=session,
        approvals=approvals,
        code="1",  # ALLOW_ONCE
        resolved=resolved,
    )
    try:
        h.script(
            [
                ToolCall("run_terminal_command", {"command": "echo TG_CONFIRM_OK"}),
                Final("Telegram approved; terminal printed TG_CONFIRM_OK."),
            ]
        )
        result = await h.run(
            "Run echo TG_CONFIRM_OK",
            conversation_id="uc22_tg",
        )
    finally:
        h.agent.events.unsubscribe(handler)
        await h.close()

    result.assert_no_error_events()
    result.assert_confirmation_requested("run_terminal_command")
    assert resolved == ["run_terminal_command"]
    out = result.tool_result_text("run_terminal_command")
    assert "TG_CONFIRM_OK" in out
    assert "denied" not in out.lower()
    result.assert_final_contains("TG_CONFIRM_OK")


@pytest.mark.user_case
@pytest.mark.integration
@pytest.mark.asyncio
async def test_uc22_telegram_confirm_deny_blocks_terminal(
    temp_dir, monkeypatch: pytest.MonkeyPatch
):
    """UC-22b: Telegram deny callback blocks high-risk terminal."""
    h = UserCaseHarness(temp_dir, monkeypatch, config_overrides=dict(_INTERACTIVE))
    await h.setup()
    assert h.agent is not None

    session = ChatSession(
        chat_id=4243,
        user_id=8,
        profile="default",
        conversation_id="uc22_tg_deny",
    )
    session.agent = h.agent
    bot = AsyncMock()
    approvals = TelegramApprovals(bot, session)
    resolved: list[str] = []
    handler = _wire_telegram_confirm(
        agent=h.agent,
        session=session,
        approvals=approvals,
        code="4",  # DENY
        resolved=resolved,
    )
    try:
        h.script(
            [
                ToolCall("run_terminal_command", {"command": "echo SHOULD_NOT_RUN"}),
                Final("Denied via Telegram confirmation."),
            ]
        )
        result = await h.run(
            "Run echo SHOULD_NOT_RUN",
            conversation_id="uc22_tg_deny",
        )
    finally:
        h.agent.events.unsubscribe(handler)
        await h.close()

    result.assert_no_error_events()
    result.assert_confirmation_requested("run_terminal_command")
    assert resolved == ["run_terminal_command"]
    out = result.tool_result_text("run_terminal_command")
    assert "denied" in out.lower() or out.lower().startswith("error:")
    result.assert_final_contains("Denied")
