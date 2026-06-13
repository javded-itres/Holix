"""Confirmation and plan-review flows via Telegram inline keyboards."""

from __future__ import annotations

import secrets
from typing import Any

from core.plan_review.review_events import PlanReviewRequestEvent
from core.plan_review.review_guard import PlanReviewChoice, get_plan_review_guard
from core.security.confirmation import ConfirmationChoice, get_action_guard
from core.security.confirmation_events import ConfirmationRequestEvent

from integrations.telegram.markdown import escape_html, plain_to_telegram_html

# Telegram Bot API: callback_data must be 1–64 bytes.
_TELEGRAM_CALLBACK_MAX_BYTES = 64


def _register_callback_token(mapping: dict[str, str], full_id: str) -> str:
    """Map a short opaque token to the full confirmation/review id."""
    mapping.clear()
    token = secrets.token_hex(4)
    mapping[token] = full_id
    return token


def _lookup_callback_token(mapping: dict[str, str], token_or_id: str) -> str:
    """Resolve short token; pass through when already a full id."""
    return mapping.get(token_or_id, token_or_id)


def _callback_data(*parts: str) -> str:
    data = ":".join(parts)
    if len(data.encode("utf-8")) > _TELEGRAM_CALLBACK_MAX_BYTES:
        raise ValueError(f"Telegram callback_data too long ({len(data.encode('utf-8'))} bytes)")
    return data


class TelegramApprovals:
    def __init__(self, bot: Any, session: Any) -> None:
        self._bot = bot
        self._session = session
        self._pending_confirm_id: str | None = None
        self._pending_review_id: str | None = None

    async def on_confirmation_request(self, event: ConfirmationRequestEvent) -> None:
        await self.dismiss_confirmation_ui()
        self._pending_confirm_id = event.confirmation_id
        token = _register_callback_token(
            self._session.approval_callback_tokens,
            event.confirmation_id,
        )
        risk = event.risk_level or "?"
        subagent = getattr(event, "subagent_name", "") or ""
        header = "<b>⚠ Confirmation required</b>"
        if subagent:
            header = f"<b>⚠ Sub-agent <code>{escape_html(subagent)}</code> needs approval</b>"
        text = (
            f"{header}\n"
            f"Tool: <code>{escape_html(event.tool_name)}</code>\n"
            f"Risk: {escape_html(risk)}\n"
            f"{escape_html(event.reason)}"
        )
        args_block = _format_confirmation_args(event.tool_name, event.arguments or {})
        if args_block:
            text += "\n\n" + args_block

        # Telegram hard limit ~4096; leave headroom for keyboard
        if len(text) > 3500:
            text = text[:3500] + "…"

        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✓ Once",
                        callback_data=_callback_data("cfm", token, "1"),
                    ),
                    InlineKeyboardButton(
                        text="✓ Session",
                        callback_data=_callback_data("cfm", token, "2"),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="✓ Always",
                        callback_data=_callback_data("cfm", token, "3"),
                    ),
                    InlineKeyboardButton(
                        text="✗ Deny",
                        callback_data=_callback_data("cfm", token, "4"),
                    ),
                ],
            ]
        )
        sent = await self._bot.send_message(
            self._session.chat_id,
            text,
            parse_mode="HTML",
            reply_markup=kb,
        )
        self._session.pending_confirmation_message_id = sent.message_id

    async def on_plan_review_request(self, event: PlanReviewRequestEvent) -> None:
        await self.dismiss_plan_review_ui()
        self._pending_review_id = event.review_id
        self._session.pending_plan_review_id = event.review_id
        token = _register_callback_token(
            self._session.plan_callback_tokens,
            event.review_id,
        )
        body = event.rendered_markdown or f"Plan with {event.step_count} steps"
        if len(body) > 3500:
            body = body[:3500] + "…"
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Confirm step",
                        callback_data=_callback_data("plan", token, "confirm"),
                    ),
                    InlineKeyboardButton(
                        text="Auto-run",
                        callback_data=_callback_data("plan", token, "auto"),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="Refine",
                        callback_data=_callback_data("plan", token, "refine"),
                    ),
                    InlineKeyboardButton(
                        text="Reject",
                        callback_data=_callback_data("plan", token, "reject"),
                    ),
                ],
            ]
        )
        plan_msg = await self._bot.send_message(
            self._session.chat_id,
            plain_to_telegram_html(body),
            parse_mode="HTML",
            reply_markup=kb,
        )
        hint_msg = await self._bot.send_message(
            self._session.chat_id,
            "<i>Or reply with text to refine the plan.</i>",
            parse_mode="HTML",
        )
        self._session.pending_plan_message_ids = [
            plan_msg.message_id,
            hint_msg.message_id,
        ]

    async def dismiss_confirmation_ui(self) -> None:
        """Remove the inline-keyboard confirmation prompt from the chat."""
        message_id = self._session.pending_confirmation_message_id
        self._session.pending_confirmation_message_id = None
        if message_id is not None:
            await self._delete_message_safe(message_id)

    async def dismiss_plan_review_ui(self) -> None:
        """Remove plan review prompt messages (plan body + hint)."""
        message_ids = list(self._session.pending_plan_message_ids)
        self._session.pending_plan_message_ids = []
        for message_id in message_ids:
            await self._delete_message_safe(message_id)

    async def _delete_message_safe(self, message_id: int) -> None:
        try:
            await self._bot.delete_message(self._session.chat_id, message_id)
        except Exception:
            pass

    def resolve_confirmation_callback(self, confirmation_id: str, code: str) -> bool:
        choice_map = {
            "1": ConfirmationChoice.ALLOW_ONCE,
            "2": ConfirmationChoice.ALLOW_SESSION,
            "3": ConfirmationChoice.ALLOW_ALWAYS,
            "4": ConfirmationChoice.DENY,
        }
        choice = choice_map.get(code)
        if choice is None:
            return False

        full_id = _lookup_callback_token(
            self._session.approval_callback_tokens,
            confirmation_id,
        )
        if self._try_resolve_confirmation(full_id, choice):
            self._pending_confirm_id = None
            self._session.approval_callback_tokens.clear()
            return True

        # Fallback: match /yes behaviour (latest pending on this agent).
        agent = self._session.agent
        if agent:
            from core.subagents.interaction import resolve_any_confirmation

            if resolve_any_confirmation(agent, choice):
                self._pending_confirm_id = None
                self._session.approval_callback_tokens.clear()
                return True

        # Idempotent: user double-tapped after the action was already approved.
        if self._confirmation_already_resolved(full_id):
            self._pending_confirm_id = None
            self._session.approval_callback_tokens.clear()
            return True
        return False

    def _try_resolve_confirmation(
        self,
        confirmation_id: str,
        choice: ConfirmationChoice,
    ) -> bool:
        agent = self._session.agent
        if agent:
            from core.subagents.interaction import get_interaction_bridge

            bridge = get_interaction_bridge(agent)
            if bridge and bridge.resolve_confirmation(confirmation_id, choice):
                return True

        guard = self._guard()
        return bool(guard and guard.resolve_confirmation(confirmation_id, choice))

    def _confirmation_already_resolved(self, confirmation_id: str) -> bool:
        """True when the request id is unknown because it was already settled."""
        agent = self._session.agent
        if agent:
            from core.subagents.interaction import get_interaction_bridge

            bridge = get_interaction_bridge(agent)
            if bridge and confirmation_id in getattr(bridge, "_pending_confirmations", {}):
                return False

        guard = self._guard()
        if guard and confirmation_id in guard._pending_confirmations:
            return False
        token = confirmation_id
        if token in self._session.approval_callback_tokens:
            return False
        return self._pending_confirm_id in (None, confirmation_id)

    def _guard(self):
        """Resolve ActionGuard for the active Telegram session agent."""
        agent = self._session.agent
        if agent and getattr(agent, "tools", None):
            ag = getattr(agent.tools, "_action_guard", None)
            if ag:
                return ag
        profile = getattr(self._session, "profile", None)
        return get_action_guard(profile)

    def _plan_guard(self):
        """PlanReviewGuard tied to this chat's agent (not a stale global)."""
        agent = self._session.agent
        if agent:
            guard = getattr(agent, "_plan_review_guard", None)
            if guard:
                return guard
        return get_plan_review_guard()

    def resolve_plan_callback(self, review_id: str, action: str, *, feedback: str = "") -> bool:
        action_map = {
            "confirm": PlanReviewChoice.CONFIRM_STEP,
            "auto": PlanReviewChoice.AUTO_EXECUTE,
            "refine": PlanReviewChoice.REFINE,
            "reject": PlanReviewChoice.REJECT,
        }
        choice = action_map.get(action)
        if choice is None:
            return False

        full_id = _lookup_callback_token(self._session.plan_callback_tokens, review_id)
        guard = self._plan_guard()
        if guard and guard.resolve_review(full_id, choice, feedback):
            self._pending_review_id = None
            self._session.pending_plan_review_id = None
            self._session.plan_callback_tokens.clear()
            return True

        # Fallback: latest pending review on this agent's guard.
        if guard and guard._pending_reviews:
            latest_id = list(guard._pending_reviews.keys())[-1]
            if guard.resolve_review(latest_id, choice, feedback):
                self._pending_review_id = None
                self._session.pending_plan_review_id = None
                self._session.plan_callback_tokens.clear()
                return True

        if self._pending_review_id in (None, full_id, review_id):
            self._session.plan_callback_tokens.clear()
            return True
        return False

    def resolve_plan_text(self, message: str) -> bool:
        if not self._session.pending_plan_review_id:
            return False
        choice, feedback = _parse_plan_text(message)
        action = {
            PlanReviewChoice.CONFIRM_STEP: "confirm",
            PlanReviewChoice.AUTO_EXECUTE: "auto",
            PlanReviewChoice.REFINE: "refine",
            PlanReviewChoice.REJECT: "reject",
        }[choice]
        return self.resolve_plan_callback(
            self._session.pending_plan_review_id,
            action,
            feedback=feedback,
        )


def _parse_plan_text(text: str) -> tuple[PlanReviewChoice, str]:
    text_stripped = text.strip()
    text_clean = text_stripped.lower().rstrip("!.,;:?!")
    confirm_words = {
        "да", "yes", "ок", "ok", "confirm", "выполняй", "давай",
        "согласен", "подтверждаю", "запускай", "go", "поехали",
    }
    reject_words = {"нет", "no", "отмена", "cancel", "reject", "стоп", "stop"}
    if text_clean in confirm_words:
        return PlanReviewChoice.AUTO_EXECUTE, ""
    if text_clean in reject_words:
        return PlanReviewChoice.REJECT, ""
    return PlanReviewChoice.REFINE, text_stripped


def _format_confirmation_args(tool_name: str, args: dict) -> str:
    """Produce compact HTML snippet showing the key command/args for a confirmation prompt.

    This is shown in the dedicated confirmation message sent to Telegram so the
    user sees exactly what will be executed (instead of a generic "Confirmation: tool").
    """
    if not args:
        return ""
    try:
        if tool_name == "run_terminal_command":
            cmd = args.get("command") or args.get("cmd") or ""
            if cmd:
                cmd = str(cmd)[:1600]
                return f"<b>Command:</b>\n<pre>{escape_html(cmd)}</pre>"
        elif tool_name == "write_file":
            path = args.get("path", "")
            content = str(args.get("content", "") or "")[:700]
            parts = [f"<b>Path:</b> <code>{escape_html(str(path))}</code>"]
            if content:
                parts.append(f"<b>Content preview:</b>\n<pre>{escape_html(content)}</pre>")
            return "\n".join(parts)
        elif tool_name == "execute_python":
            code = str(args.get("code", "") or "")[:700]
            if code:
                return f"<b>Python code:</b>\n<pre>{escape_html(code)}</pre>"
        # generic fallback
        import json

        j = json.dumps(args, ensure_ascii=False, indent=2)[:900]
        return f"<b>Arguments:</b>\n<pre>{escape_html(j)}</pre>"
    except Exception:
        safe = escape_html(str(args)[:400])
        return f"<b>Arguments:</b> <code>{safe}</code>"