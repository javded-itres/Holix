"""Confirmation and plan-review flows via MAX inline keyboards."""

from __future__ import annotations

import json
import secrets
from typing import Any

from core.plan_review.review_events import PlanReviewRequestEvent
from core.plan_review.review_guard import PlanReviewChoice, get_plan_review_guard
from core.security.confirmation import ConfirmationChoice, get_action_guard
from core.security.confirmation_events import ConfirmationRequestEvent

from integrations.max.client import MaxClient
from integrations.max.keyboards import confirmation_keyboard, plan_review_keyboard
from integrations.max.markdown import plain_to_max_html
from integrations.max.models import message_id_from_response, reply_kwargs_for_session


def _register_callback_token(mapping: dict[str, str], full_id: str) -> str:
    """Map a short opaque token to the full confirmation/review id."""
    mapping.clear()
    token = secrets.token_hex(4)
    mapping[token] = full_id
    return token


def _lookup_callback_token(mapping: dict[str, str], token_or_id: str) -> str:
    """Resolve short token; pass through when already a full id."""
    return mapping.get(token_or_id, token_or_id)


class MaxApprovals:
    def __init__(self, client: MaxClient, session: Any) -> None:
        self._client = client
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
        header = "**⚠ Confirmation required**"
        if subagent:
            header = f"**⚠ Sub-agent `{subagent}` needs approval**"
        text = (
            f"{header}\n"
            f"Tool: `{event.tool_name}`\n"
            f"Risk: {risk}\n"
            f"{event.reason}"
        )
        args_block = _format_confirmation_args(event.tool_name, event.arguments or {})
        if args_block:
            text += "\n\n" + args_block
        if len(text) > 3500:
            text = text[:3500] + "…"

        payload = await self._client.send_message(
            plain_to_max_html(text),
            fmt="html",
            attachments=[confirmation_keyboard(token)],
            **reply_kwargs_for_session(
                user_id=self._session.user_id,
                reply_user_id=self._session.reply_user_id,
                reply_chat_id=self._session.reply_chat_id,
                chat_type=self._session.chat_type,
            ),
        )
        self._session.pending_confirmation_message_id = message_id_from_response(payload)

    async def on_plan_review_request(self, event: PlanReviewRequestEvent) -> None:
        await self.dismiss_plan_review_ui()
        self._pending_review_id = event.review_id
        self._session.pending_plan_review_id = event.review_id
        self._session.pending_plan_phase = getattr(event, "phase", "approval") or "approval"
        token = _register_callback_token(
            self._session.plan_callback_tokens,
            event.review_id,
        )
        body = event.rendered_markdown or f"Plan with {event.step_count} steps"
        if len(body) > 3500:
            body = body[:3500] + "…"

        reply = reply_kwargs_for_session(
            user_id=self._session.user_id,
            reply_user_id=self._session.reply_user_id,
            reply_chat_id=self._session.reply_chat_id,
            chat_type=self._session.chat_type,
        )
        plan_payload = await self._client.send_message(
            plain_to_max_html(body),
            fmt="html",
            attachments=[plan_review_keyboard(token)],
            **reply,
        )
        from integrations.messenger.locale import messenger_locale
        from core.i18n.messages import t

        lang = messenger_locale(self._session.profile)
        hint_key = (
            "plan.clarify.hint"
            if self._session.pending_plan_phase == "clarification"
            else "plan.refine_hint"
        )
        hint_payload = await self._client.send_message(
            plain_to_max_html(t(hint_key, lang)),
            fmt="html",
            **reply,
        )
        ids: list[str] = []
        for p in (plan_payload, hint_payload):
            mid = message_id_from_response(p)
            if mid:
                ids.append(mid)
        self._session.pending_plan_message_ids = ids

    async def dismiss_confirmation_ui(self) -> None:
        message_id = self._session.pending_confirmation_message_id
        self._session.pending_confirmation_message_id = None
        if message_id:
            await self._delete_message_safe(message_id)

    async def dismiss_plan_review_ui(self) -> None:
        message_ids = list(self._session.pending_plan_message_ids)
        self._session.pending_plan_message_ids = []
        for message_id in message_ids:
            await self._delete_message_safe(message_id)

    async def _delete_message_safe(self, message_id: str) -> None:
        try:
            await self._client.delete_message(message_id)
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

        agent = self._session.agent
        if agent:
            from core.subagents.interaction import resolve_any_confirmation

            if resolve_any_confirmation(agent, choice):
                self._pending_confirm_id = None
                self._session.approval_callback_tokens.clear()
                return True

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
        agent = self._session.agent
        if agent and getattr(agent, "tools", None):
            ag = getattr(agent.tools, "_action_guard", None)
            if ag:
                return ag
        profile = getattr(self._session, "profile", None)
        return get_action_guard(profile)

    def _plan_guard(self):
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
            "proceed": PlanReviewChoice.PROCEED_ASSUMPTIONS,
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
        choice, feedback = _parse_plan_text(
            message,
            phase=getattr(self._session, "pending_plan_phase", "approval"),
        )
        action = {
            PlanReviewChoice.CONFIRM_STEP: "confirm",
            PlanReviewChoice.AUTO_EXECUTE: "auto",
            PlanReviewChoice.REFINE: "refine",
            PlanReviewChoice.REJECT: "reject",
            PlanReviewChoice.PROCEED_ASSUMPTIONS: "proceed",
        }[choice]
        return self.resolve_plan_callback(
            self._session.pending_plan_review_id,
            action,
            feedback=feedback,
        )


def _parse_plan_text(text: str, *, phase: str = "approval") -> tuple[PlanReviewChoice, str]:
    from core.plan_review.clarification import parse_plan_review_response

    choice_value, feedback = parse_plan_review_response(text, phase=phase)
    return PlanReviewChoice(choice_value), feedback


def _format_confirmation_args(tool_name: str, args: dict) -> str:
    if not args:
        return ""
    try:
        if tool_name == "run_terminal_command":
            cmd = args.get("command") or args.get("cmd") or ""
            if cmd:
                return f"**Command:**\n```\n{str(cmd)[:1600]}\n```"
        if tool_name == "write_file":
            path = args.get("path", "")
            content = str(args.get("content", "") or "")[:700]
            parts = [f"**Path:** `{path}`"]
            if content:
                parts.append(f"**Content preview:**\n```\n{content}\n```")
            return "\n".join(parts)
        if tool_name == "execute_python":
            code = str(args.get("code", "") or "")[:700]
            if code:
                return f"**Python code:**\n```\n{code}\n```"
        j = json.dumps(args, ensure_ascii=False, indent=2)[:900]
        return f"**Arguments:**\n```\n{j}\n```"
    except Exception:
        return f"**Arguments:** `{str(args)[:400]}`"