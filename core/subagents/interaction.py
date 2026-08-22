"""
Bridge sub-agent questions and process-mode confirmations to the main chat stream.

Async sub-agents reuse the parent ActionGuard for tool confirmations (with
subagent_name on ConfirmationRequestEvent). Process sub-agents and ask_user
use IPC + this bridge so the user can approve or answer in TUI / Telegram
while the main agent keeps handling other messages.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from core.security.confirmation import ConfirmationChoice
from core.security.confirmation_events import ConfirmationRequestEvent
from core.subagents.interaction_events import SubAgentQuestionEvent

logger = logging.getLogger(__name__)

# Messengers replace this with a button picker; CLI/TUI format a typed hint.
SUBAGENT_REPLY_NEED_TARGET = "NEED_SUBAGENT_TARGET"


class SubAgentInteractionBridge:
    """Routes sub-agent IPC prompts to the parent event bus and awaits replies."""

    def __init__(self, parent_agent: Any, *, confirmation_timeout: int = 0):
        self._parent = parent_agent
        self._confirmation_timeout = confirmation_timeout
        self._pending_confirmations: dict[str, asyncio.Future] = {}
        self._pending_questions: dict[str, asyncio.Future] = {}

    @property
    def pending_question_ids(self) -> list[str]:
        return list(self._pending_questions.keys())

    def pending_question_for(self, request_id: str) -> dict | None:
        """Return metadata for a pending question request."""
        if request_id not in self._pending_questions:
            return None
        meta = getattr(self, "_question_meta", {}).get(request_id)
        return meta

    def list_pending_questions(self) -> list[dict]:
        """Summaries for UI hints (/subagent-reply, routing)."""
        meta = getattr(self, "_question_meta", {})
        return [
            {
                "request_id": rid,
                "subagent_name": meta.get(rid, {}).get("subagent_name", ""),
                "question": meta.get(rid, {}).get("question", ""),
            }
            for rid in self._pending_questions
        ]

    async def handle_ipc_confirmation(self, subagent_name: str, metadata: dict) -> str:
        """Wait for user approval after a process sub-agent emits confirmation_request."""
        request_id = metadata.get("request_id") or f"subcfm_{uuid.uuid4().hex[:10]}"
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_confirmations[request_id] = future

        event_bus = getattr(self._parent, "events", None)
        if event_bus:
            parent_ctx = getattr(self._parent, "_event_context", None)
            parent_cid = str(getattr(parent_ctx, "conversation_id", None) or "").strip()
            event = ConfirmationRequestEvent(
                confirmation_id=request_id,
                tool_name=metadata.get("tool_name", ""),
                arguments=metadata.get("arguments") or {},
                risk_level=metadata.get("risk_level", "medium"),
                reason=metadata.get("reason", ""),
                pattern_matched=metadata.get("pattern_matched"),
                subagent_name=subagent_name,
                conversation_id=parent_cid or "default",
            )
            # Prefer agent.emit so stamp_event fills run_id/plan_id when available.
            emit = getattr(self._parent, "emit", None)
            if callable(emit):
                emit(event)
            else:
                event_bus.emit(event)
            logger.info(
                "Sub-agent '%s' confirmation surfaced (id=%s, tool=%s)",
                subagent_name,
                request_id,
                metadata.get("tool_name"),
            )

        timeout = self._confirmation_timeout if self._confirmation_timeout > 0 else None
        try:
            choice = await asyncio.wait_for(future, timeout=timeout)
            return choice.value if isinstance(choice, ConfirmationChoice) else str(choice)
        except TimeoutError:
            return ConfirmationChoice.DENY.value
        finally:
            self._pending_confirmations.pop(request_id, None)

    async def handle_ipc_question(self, subagent_name: str, metadata: dict) -> str:
        """Wait for a user answer after a sub-agent emits a question IPC message."""
        request_id = metadata.get("request_id") or f"subq_{uuid.uuid4().hex[:10]}"
        question = metadata.get("question", "")
        context = metadata.get("context", "")

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_questions[request_id] = future
        if not hasattr(self, "_question_meta"):
            self._question_meta: dict[str, dict] = {}
        parent_ctx = getattr(self._parent, "_event_context", None)
        parent_cid = str(getattr(parent_ctx, "conversation_id", None) or "").strip()
        self._question_meta[request_id] = {
            "subagent_name": subagent_name,
            "question": question,
            "context": context,
            "conversation_id": parent_cid,
        }

        event_bus = getattr(self._parent, "events", None)
        if event_bus:
            event = SubAgentQuestionEvent(
                request_id=request_id,
                subagent_name=subagent_name,
                question=question,
                context=context,
                conversation_id=parent_cid or "default",
            )
            emit = getattr(self._parent, "emit", None)
            if callable(emit):
                emit(event)
            else:
                event_bus.emit(event)
            q_preview = (question or "").replace("\n", " ").strip()
            if len(q_preview) > 240:
                q_preview = q_preview[:239] + "…"
            ctx_preview = (context or "").replace("\n", " ").strip()
            if len(ctx_preview) > 120:
                ctx_preview = ctx_preview[:119] + "…"
            logger.info(
                "Sub-agent '%s' question surfaced (id=%s): %s%s",
                subagent_name,
                request_id,
                q_preview or "(empty)",
                f" | context={ctx_preview}" if ctx_preview else "",
            )

        timeout = self._confirmation_timeout if self._confirmation_timeout > 0 else None
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            return "Error: question timed out — no answer from user"
        finally:
            self._pending_questions.pop(request_id, None)
            self._question_meta.pop(request_id, None)

    async def ask_user(
        self,
        subagent_name: str,
        question: str,
        *,
        context: str = "",
    ) -> str:
        """In-process ask_user for async sub-agents (same event bus, no IPC)."""
        return await self.handle_ipc_question(
            subagent_name,
            {
                "request_id": f"subq_{uuid.uuid4().hex[:10]}",
                "question": question,
                "context": context,
            },
        )

    def resolve_confirmation(self, request_id: str, choice: ConfirmationChoice) -> bool:
        future = self._pending_confirmations.get(request_id)
        if future is None or future.done():
            return False
        future.set_result(choice)
        return True

    def resolve_confirmation_latest(self, choice: ConfirmationChoice) -> bool:
        if not self._pending_confirmations:
            return False
        request_id = list(self._pending_confirmations.keys())[-1]
        return self.resolve_confirmation(request_id, choice)

    def resolve_question(self, request_id: str, answer: str) -> bool:
        future = self._pending_questions.get(request_id)
        if future is None or future.done():
            return False
        future.set_result(answer)
        return True

    def resolve_question_for_subagent(self, subagent_name: str, answer: str) -> bool:
        """Resolve the oldest pending question for a given sub-agent job id."""
        for request_id, meta in getattr(self, "_question_meta", {}).items():
            if meta.get("subagent_name") == subagent_name and request_id in self._pending_questions:
                return self.resolve_question(request_id, answer)
        return False

    def resolve_single_pending_question(self, answer: str) -> bool:
        """When exactly one question is pending, treat free text as the answer."""
        if len(self._pending_questions) != 1:
            return False
        request_id = next(iter(self._pending_questions))
        return self.resolve_question(request_id, answer)

    def has_bridge_confirmation(self) -> bool:
        return bool(self._pending_confirmations)

    def has_pending_questions(self) -> bool:
        return bool(self._pending_questions)


def get_interaction_bridge(agent: Any) -> SubAgentInteractionBridge | None:
    subagents = getattr(agent, "subagents", None)
    if subagents is None:
        return None
    return getattr(subagents, "interactions", None)


def resolve_any_confirmation(
    agent: Any,
    choice: ConfirmationChoice,
    *,
    confirmation_id: str | None = None,
) -> bool:
    """Resolve a pending confirmation from process sub-agents or the main ActionGuard.

    Prefer an explicit ``confirmation_id`` (from the modal that was shown).
    Without it, resolve the latest pending on the ActionGuard first (async
    sub-agents), then the process-mode bridge.
    """
    cid = (confirmation_id or "").strip() or None

    guard = None
    if agent and getattr(agent, "tools", None):
        guard = getattr(agent.tools, "_action_guard", None)
    if guard is None:
        from core.security.confirmation import get_action_guard

        guard = get_action_guard()

    bridge = get_interaction_bridge(agent)

    if cid:
        if guard and guard.resolve_confirmation(cid, choice):
            return True
        if bridge and bridge.resolve_confirmation(cid, choice):
            return True
        return False

    # Prefer ActionGuard (async sub-agents share it) over the process IPC bridge.
    if guard and guard._pending_confirmations:
        if hasattr(guard, "resolve_confirmation_latest"):
            if guard.resolve_confirmation_latest(choice):
                return True
        else:
            latest = list(guard._pending_confirmations.keys())[-1]
            if guard.resolve_confirmation(latest, choice):
                return True

    if bridge and bridge.resolve_confirmation_latest(choice):
        return True
    return False


def try_route_subagent_reply(agent: Any, message: str) -> tuple[bool, str]:
    """
    Deliver free text to a waiting sub-agent question.

    Supports:
    - /subagent-reply <job_id> <answer>
    - @<job_id> <answer>
    - plain text when exactly one question is pending
    """
    bridge = get_interaction_bridge(agent)
    if bridge is None or not bridge.has_pending_questions():
        return False, ""

    text = message.strip()
    lower = text.lower()

    if lower.startswith("/subagent-reply"):
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            return True, "Usage: /subagent-reply <job_id> <answer>"
        job_id, answer = parts[1], parts[2]
        if bridge.resolve_question_for_subagent(job_id, answer):
            return True, f"reply sent to {job_id}"
        return True, f"no pending question for {job_id}"

    if text.startswith("@"):
        parts = text.split(maxsplit=1)
        head = parts[0][1:]
        if head and len(parts) == 2:
            if bridge.resolve_question_for_subagent(head, parts[1]):
                return True, f"reply sent to {head}"

    if bridge.resolve_single_pending_question(text):
        pending = bridge.list_pending_questions()
        name = pending[0]["subagent_name"] if pending else "sub-agent"
        return True, f"reply sent to {name}"

    return True, SUBAGENT_REPLY_NEED_TARGET


def format_need_target_hint(agent: Any) -> str:
    """CLI/TUI copy when several sub-agents wait and the text was not addressed."""
    bridge = get_interaction_bridge(agent)
    names = ", ".join(
        q.get("subagent_name") or "sub-agent"
        for q in (bridge.list_pending_questions() if bridge else [])
    )
    return (
        f"sub-agent(s) waiting for input: {names}. "
        "Reply with /subagent-reply <job_id> <answer> or @<job_id> answer"
    )
