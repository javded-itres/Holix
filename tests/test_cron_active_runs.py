"""Tests for cron active run registry."""

from __future__ import annotations

import asyncio

import pytest
from core.cron import active_runs


@pytest.mark.asyncio
async def test_cancel_marks_event_and_cancels_task() -> None:
    active_runs.begin("job-1")

    async def sleeper():
        await asyncio.sleep(5)

    task = asyncio.create_task(sleeper())
    active_runs.register_task("job-1", task)
    assert active_runs.cancel("job-1") is True
    with pytest.raises(asyncio.CancelledError):
        await task
    active_runs.clear("job-1")