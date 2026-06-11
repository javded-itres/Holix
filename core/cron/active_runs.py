"""Track in-flight cron job runs for cancellation (Hermes DELETE parity)."""

from __future__ import annotations

import asyncio
from typing import Any

_tasks: dict[str, asyncio.Task[Any]] = {}
_cancel_events: dict[str, asyncio.Event] = {}


def begin(job_id: str) -> asyncio.Event:
    """Register a new run; returns a cancel event checked by the runner."""
    cancel = asyncio.Event()
    _cancel_events[job_id] = cancel
    return cancel


def register_task(job_id: str, task: asyncio.Task[Any]) -> None:
    _tasks[job_id] = task


def cancel(job_id: str) -> bool:
    """Request cancellation of an in-flight job run."""
    had_activity = False
    cancel = _cancel_events.get(job_id)
    if cancel is not None:
        cancel.set()
        had_activity = True
    task = _tasks.get(job_id)
    if task is not None and not task.done():
        task.cancel()
        had_activity = True
    return had_activity


def is_cancelled(job_id: str) -> bool:
    cancel = _cancel_events.get(job_id)
    return cancel is not None and cancel.is_set()


def is_active(job_id: str) -> bool:
    task = _tasks.get(job_id)
    if task is not None and not task.done():
        return True
    return job_id in _cancel_events and not is_cancelled(job_id)


def clear(job_id: str) -> None:
    _tasks.pop(job_id, None)
    _cancel_events.pop(job_id, None)