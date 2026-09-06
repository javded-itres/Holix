"""Interactive Continue/Abort pause when the main-agent step budget is exhausted.

Sub-agents and unattended runs skip this and stop with a step-limit message.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any

logger = logging.getLogger(__name__)

CONTINUE = "continue"
ABORT = "abort"

_pending: dict[str, asyncio.Future[str]] = {}
_payloads: dict[str, dict[str, Any]] = {}


def can_ask_user(
    agent: Any | None,
    *,
    conversation_id: str = "",
    user_used: int = 0,
    policy: Any | None = None,
) -> bool:
    """True when the main interactive agent can pause for Continue/Abort."""
    if agent is None:
        return False
    # Pytest has no Continue/Abort UI; waiting forever hangs CI.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    if policy is not None:
        user_max = int(getattr(policy, "user_max_extensions", 0) or 0)
        if user_max <= 0 or int(user_used) >= user_max:
            return False
    cfg = getattr(agent, "config", None)
    if cfg is not None and bool(getattr(cfg, "non_interactive", False)):
        return False
    try:
        from core.di.runtime_config import unattended_requested

        if unattended_requested():
            return False
    except Exception:
        pass
    prompt = getattr(agent, "subagent_system_prompt", None)
    if isinstance(prompt, str) and prompt.strip():
        return False
    cid = str(conversation_id or "")
    if cid.startswith("subagent:"):
        return False
    try:
        from core.tools.execution_context import get_subagent_name

        if get_subagent_name():
            return False
    except Exception:
        pass
    return True


def snapshot_pending() -> list[dict[str, Any]]:
    """Still-waiting Continue/Abort prompts (Studio WS reconnect)."""
    out: list[dict[str, Any]] = []
    for request_id, future in list(_pending.items()):
        if future.done():
            continue
        payload = dict(_payloads.get(request_id) or {})
        payload.setdefault("request_id", request_id)
        out.append(payload)
    return out


def pending_ids() -> list[str]:
    return [rid for rid, fut in _pending.items() if not fut.done()]


def resolve_step_budget(request_id: str, choice: str) -> bool:
    """Resolve a pending Continue/Abort prompt. Returns True if a waiter was woken."""
    rid = str(request_id or "").strip()
    if not rid:
        return resolve_step_budget_latest(choice)
    future = _pending.get(rid)
    if future is None or future.done():
        return False
    normalized = _normalize_choice(choice)
    try:
        future.set_result(normalized)
    except Exception:
        return False
    logger.info("step budget resolved %s → %s", rid, normalized)
    return True


def resolve_step_budget_latest(choice: str) -> bool:
    if not _pending:
        return False
    return resolve_step_budget(list(_pending.keys())[-1], choice)


def abort_all_pending_step_budget(*, conversation_id: str | None = None) -> int:
    """Wake waiters with abort (Stop / session teardown)."""
    woken = 0
    cid = str(conversation_id or "").strip()
    for request_id, payload in list(_payloads.items()):
        if cid and str(payload.get("conversation_id") or "") not in {cid, ""}:
            continue
        if resolve_step_budget(request_id, ABORT):
            woken += 1
    return woken


def _normalize_choice(raw: str) -> str:
    text = str(raw or "").strip().lower()
    if text in {
        CONTINUE,
        "c",
        "1",
        "yes",
        "y",
        "ok",
        "продолжить",
        "продолжай",
        "да",
    }:
        return CONTINUE
    return ABORT


async def ask_continue_or_abort(
    *,
    agent: Any | None,
    conversation_id: str,
    step_count: int,
    max_steps: int,
    extra_steps: int,
    user_used: int,
    user_max: int,
    reason: str = "",
    locale: str = "en",
) -> str:
    """Emit StepBudgetChoiceEvent and wait until the user picks Continue or Abort."""
    from core.agent_events import StepBudgetChoiceEvent, StepBudgetResolvedEvent
    from core.presenters.final_content import step_limit_reached_message

    request_id = f"sb_{uuid.uuid4().hex[:12]}"
    loc = (locale or "en").strip().lower()[:2]
    remaining = max(0, int(user_max) - int(user_used))
    message = step_limit_reached_message(
        int(max_steps),
        step_count=int(step_count),
        extra_steps=int(extra_steps),
        locale=loc,
    )
    if loc == "ru":
        continue_label = "Продолжить"
        abort_label = "Прервать"
        if remaining:
            message += f" Осталось продлений: {remaining}/{user_max}."
    else:
        continue_label = "Continue"
        abort_label = "Abort"
        if remaining:
            message += f" Continues remaining: {remaining}/{user_max}."
    if reason:
        message += f"\n({reason})"

    choices = [
        {"code": CONTINUE, "label": continue_label},
        {"code": ABORT, "label": abort_label},
    ]
    payload = {
        "request_id": request_id,
        "conversation_id": conversation_id,
        "step_count": int(step_count),
        "max_steps": int(max_steps),
        "extra_steps": int(extra_steps),
        "user_extensions_used": int(user_used),
        "user_extensions_max": int(user_max),
        "reason": reason,
        "message": message,
        "choices": choices,
    }

    loop = asyncio.get_running_loop()
    future: asyncio.Future[str] = loop.create_future()
    _pending[request_id] = future
    _payloads[request_id] = payload

    if agent is not None and hasattr(agent, "emit"):
        try:
            agent.emit(
                StepBudgetChoiceEvent(
                    request_id=request_id,
                    step_count=int(step_count),
                    max_steps=int(max_steps),
                    extra_steps=int(extra_steps),
                    user_extensions_used=int(user_used),
                    user_extensions_max=int(user_max),
                    reason=reason,
                    message=message,
                    choices=choices,
                    conversation_id=conversation_id,
                )
            )
        except Exception:
            logger.debug("failed to emit StepBudgetChoiceEvent", exc_info=True)

    logger.info(
        "step budget waiting for user choice id=%s steps=%s/%s extra=+%s",
        request_id,
        step_count,
        max_steps,
        extra_steps,
    )
    try:
        return await future
    except asyncio.CancelledError:
        return ABORT
    finally:
        _pending.pop(request_id, None)
        _payloads.pop(request_id, None)
        if agent is not None and hasattr(agent, "emit"):
            try:
                agent.emit(
                    StepBudgetResolvedEvent(
                        request_id=request_id,
                        choice=_choice_if_done(future),
                        conversation_id=conversation_id,
                    )
                )
            except Exception:
                logger.debug("failed to emit StepBudgetResolvedEvent", exc_info=True)


def _choice_if_done(future: asyncio.Future[str]) -> str:
    if future.done() and not future.cancelled():
        try:
            return str(future.result() or ABORT)
        except Exception:
            return ABORT
    return ABORT
