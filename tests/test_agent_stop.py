"""Tests for /stop — cancel runs, confirmations, and plan review."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from cli.shared.agent_stop import (
    cancel_host_run_tasks,
    deny_all_pending_confirmations,
    reject_all_pending_plan_reviews,
    stop_agent_activity_sync,
)
from core.plan_review.review_guard import PlanReviewChoice, PlanReviewGuard
from core.security.confirmation import (
    ActionGuard,
    ConfirmationChoice,
    RiskLevel,
)


@pytest.mark.asyncio
async def test_deny_all_pending_confirmations_drains_guard() -> None:
    guard = ActionGuard(interactive=True, auto_allow_threshold=RiskLevel.NO)
    fut1 = asyncio.get_running_loop().create_future()
    fut2 = asyncio.get_running_loop().create_future()
    guard._pending_confirmations["c1"] = fut1
    guard._pending_confirmations["c2"] = fut2

    agent = MagicMock()
    agent.subagents = None
    agent.tools._action_guard = guard

    count = deny_all_pending_confirmations(agent)
    assert count == 2
    assert fut1.result() == ConfirmationChoice.DENY
    assert fut2.result() == ConfirmationChoice.DENY


def test_reject_all_pending_plan_reviews(monkeypatch: pytest.MonkeyPatch) -> None:
    guard = PlanReviewGuard(interactive=True)
    loop = asyncio.new_event_loop()
    try:
        fut = loop.create_future()
        guard._pending_reviews["review_1"] = fut
        monkeypatch.setattr(
            "core.plan_review.review_guard.get_plan_review_guard",
            lambda: guard,
        )
        count = reject_all_pending_plan_reviews()
        assert count == 1
        choice, feedback = fut.result()
        assert choice == PlanReviewChoice.REJECT
        assert "stopped" in feedback
    finally:
        loop.close()


def test_reject_pending_plan_reviews_for_conversation_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cli.shared.agent_stop import reject_pending_plan_reviews_for_conversation
    from core.plan_review.review_guard import (
        _GLOBAL_LOCK,
        _GLOBAL_PENDING,
        reject_global_pending_reviews_for_conversation,
    )

    loop = asyncio.new_event_loop()
    try:
        fut_a = loop.create_future()
        fut_b = loop.create_future()
        with _GLOBAL_LOCK:
            _GLOBAL_PENDING.clear()
            _GLOBAL_PENDING["plan_review_1_tab_a"] = fut_a
            _GLOBAL_PENDING["plan_review_2_tab_b"] = fut_b
        monkeypatch.setattr(
            "core.plan_review.review_guard.get_plan_review_guard",
            lambda: None,
        )
        n = reject_pending_plan_reviews_for_conversation("tab_a")
        assert n == 1
        assert fut_a.done()
        assert not fut_b.done()
        choice, feedback = fut_a.result()
        assert choice == PlanReviewChoice.REJECT
        assert "stopped" in feedback
        # Cleanup leftover
        reject_global_pending_reviews_for_conversation("tab_b")
    finally:
        with _GLOBAL_LOCK:
            _GLOBAL_PENDING.clear()
        loop.close()


@pytest.mark.asyncio
async def test_cancel_host_run_tasks() -> None:
    host = MagicMock()

    async def sleeper() -> None:
        await asyncio.sleep(60)

    task = asyncio.create_task(sleeper())
    host._run_tasks = {task}
    assert cancel_host_run_tasks(host) == 1
    await asyncio.sleep(0.05)
    assert task.cancelled() or task.done()


def test_stop_agent_activity_sync_cancels_textual_workers() -> None:
    worker = MagicMock()
    worker.name = "agent-run"
    worker.group = "agent"
    worker.node = object()

    workers = MagicMock()
    workers.__iter__ = lambda self: iter([worker])
    workers.cancel_group.return_value = [worker]

    host = MagicMock()
    host.workers = workers
    host._run_tasks = set()
    host.agent = None
    host._modals = None

    stop_agent_activity_sync(host)
    worker.cancel.assert_called_once()
    host.run_worker.assert_called_once()