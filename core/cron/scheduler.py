"""Background cron scheduler (runs inside gateway supervisor)."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from core.cron.runner import run_cron_job
from core.cron.store import CronStore

logger = logging.getLogger(__name__)

TICK_SECONDS = 30


def _parse_utc_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _job_is_due(job, *, now: datetime) -> bool:
    if not job.enabled or not job.next_run_at:
        return False
    try:
        return _parse_utc_iso(job.next_run_at) <= now
    except ValueError:
        return False


class CronScheduler:
    """Poll due jobs and dispatch agent runs."""

    def __init__(self, profile: str = "default") -> None:
        self.profile = profile
        self._store = CronStore(profile)
        self._running_jobs: set[str] = set()
        self._lock = asyncio.Lock()

    async def run_forever(self) -> None:
        logger.info("Cron scheduler started (profile=%s)", self.profile)
        self._store.refresh_all_next_runs()
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Cron tick failed")
            await asyncio.sleep(TICK_SECONDS)

    async def tick(self) -> None:
        now = datetime.now(UTC)
        for job in self._store.list_jobs(enabled_only=True):
            if job.id in self._running_jobs:
                continue
            if job.last_status == "running":
                continue
            if not _job_is_due(job, now=now):
                continue
            async with self._lock:
                if job.id in self._running_jobs:
                    continue
                self._running_jobs.add(job.id)

            asyncio.create_task(self._run_wrapped(job.id), name=f"cron-{job.id}")

    async def _run_wrapped(self, job_id: str) -> None:
        try:
            job = self._store.get(job_id)
            if job and job.enabled:
                await run_cron_job(job)
        finally:
            self._running_jobs.discard(job_id)