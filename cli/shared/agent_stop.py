"""Stop all in-flight agent work for TUI, Telegram, MAX, and CLI hosts."""

from __future__ import annotations

import asyncio
from typing import Any

AGENT_WORKER_GROUP = "agent"
AGENT_WORKER_NAMES = frozenset({"agent-stream", "agent-run"})


def deny_all_pending_confirmations(agent: Any | None) -> int:
    """Resolve every pending ActionGuard / sub-agent confirmation with DENY."""
    from core.security.confirmation import ConfirmationChoice, get_action_guard
    from core.subagents.interaction import get_interaction_bridge

    resolved = 0
    bridge = get_interaction_bridge(agent)
    if bridge is not None:
        for request_id in list(bridge._pending_confirmations.keys()):
            if bridge.resolve_confirmation(request_id, ConfirmationChoice.DENY):
                resolved += 1

    guard = None
    if agent is not None and getattr(agent, "tools", None):
        guard = getattr(agent.tools, "_action_guard", None)
    if guard is None:
        profile_name = None
        if agent is not None:
            cfg = getattr(agent, "config", None)
            if cfg is not None:
                profile_name = getattr(cfg, "profile_name", None)
        guard = get_action_guard(profile_name)
    if guard is not None:
        for confirmation_id in list(guard._pending_confirmations.keys()):
            if guard.resolve_confirmation(confirmation_id, ConfirmationChoice.DENY):
                resolved += 1
    return resolved


def reject_all_pending_plan_reviews(*, feedback: str = "stopped by user") -> int:
    """Reject all pending plan-review futures so graph execution can unwind."""
    from core.plan_review.review_guard import PlanReviewChoice, get_plan_review_guard

    guard = get_plan_review_guard()
    resolved = 0
    for _ in range(16):
        pending = getattr(guard, "_pending_reviews", None) or {}
        if not pending:
            break
        review_id = list(pending.keys())[-1]
        if not guard.resolve_review(review_id, PlanReviewChoice.REJECT, feedback):
            break
        resolved += 1
    return resolved


def dismiss_host_modals(host: Any) -> None:
    """Close TUI confirmation / plan-review waits."""
    from core.security.confirmation import ConfirmationChoice

    modals = getattr(host, "_modals", None)
    if modals is None:
        return
    if getattr(host, "_pending_confirmation", None) and hasattr(modals, "confirmation"):
        modals.confirmation.resolve(ConfirmationChoice.DENY)
    if hasattr(modals, "plan_review"):
        modals.plan_review.cancel()


def cancel_textual_agent_workers(host: Any) -> int:
    """Cancel Textual workers that run agent turns (not init/hub/deferred)."""
    workers = getattr(host, "workers", None)
    if workers is None:
        return 0

    cancelled = 0
    cancel_group = getattr(workers, "cancel_group", None)
    if callable(cancel_group):
        for worker in cancel_group(host, AGENT_WORKER_GROUP):
            cancelled += 1

    for worker in list(workers):
        if getattr(worker, "name", "") in AGENT_WORKER_NAMES:
            worker.cancel()
            cancelled += 1
    return cancelled


def cancel_host_run_tasks(host: Any) -> int:
    """Cancel asyncio tasks tracked by Telegram / MAX hosts."""
    run_tasks = getattr(host, "_run_tasks", None)
    if not run_tasks:
        return 0
    cancelled = 0
    for task in list(run_tasks):
        if not task.done():
            task.cancel()
            cancelled += 1
    return cancelled


async def terminate_running_subagents(agent: Any | None) -> None:
    subagents = getattr(agent, "subagents", None) if agent else None
    if subagents is None or not hasattr(subagents, "terminate_all"):
        return
    await subagents.terminate_all()


async def stop_all_agent_activity(host: Any) -> dict[str, int]:
    """Cancel agent runs and unblock confirmations, plan review, and sub-agents."""
    agent = getattr(host, "agent", None)

    stats = {
        "confirmations": deny_all_pending_confirmations(agent),
        "plan_reviews": reject_all_pending_plan_reviews(),
        "textual_workers": cancel_textual_agent_workers(host),
        "run_tasks": cancel_host_run_tasks(host),
    }
    dismiss_host_modals(host)
    await terminate_running_subagents(agent)
    return stats


def stop_agent_activity_sync(host: Any) -> None:
    """Synchronous portion of /stop — safe from UI thread and slash handlers."""
    agent = getattr(host, "agent", None)
    deny_all_pending_confirmations(agent)
    reject_all_pending_plan_reviews()
    dismiss_host_modals(host)
    cancel_textual_agent_workers(host)
    cancel_host_run_tasks(host)

    run_worker = getattr(host, "run_worker", None)
    if callable(run_worker):
        run_worker(
            terminate_running_subagents(agent),
            name="agent-stop",
            group=AGENT_WORKER_GROUP,
            exclusive=True,
        )
    else:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(terminate_running_subagents(agent))
        except RuntimeError:
            pass