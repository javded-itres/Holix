"""Background cron scheduler (runs inside gateway supervisor)."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime

from core.cron import active_runs
from core.cron.discovery import get_profile_index
from core.cron.runner import run_cron_job
from core.cron.store import CronStore

logger = logging.getLogger(__name__)

TICK_SECONDS = int(os.environ.get("HOLIX_CRON_TICK_SECONDS", "30"))
MAX_CONCURRENT_RUNS = int(os.environ.get("HOLIX_CRON_MAX_CONCURRENT", "4"))


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


class GlobalCronScheduler:
    """Single scheduler tick loop for cron jobs across all Holix profiles."""

    def __init__(
        self,
        *,
        tick_seconds: int = TICK_SECONDS,
        max_concurrent: int = MAX_CONCURRENT_RUNS,
    ) -> None:
        self._tick_seconds = tick_seconds
        self._max_concurrent = max(1, max_concurrent)
        self._index = get_profile_index()
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._dispatch_lock = asyncio.Lock()

    async def run_forever(self) -> None:
        logger.info(
            "Cron scheduler started (global, all profiles, max_concurrent=%s)",
            self._max_concurrent,
        )
        self._index.refresh_all_next_runs()
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Cron tick failed")
            await asyncio.sleep(self._tick_seconds)

    async def tick(self) -> None:
        now = datetime.now(UTC)
        for profile, jobs in self._index.iter_enabled_jobs():
            for job in jobs:
                if active_runs.is_active(job.id):
                    continue
                if job.last_status == "running":
                    continue
                if not _job_is_due(job, now=now):
                    continue
                async with self._dispatch_lock:
                    if active_runs.is_active(job.id):
                        continue
                    asyncio.create_task(
                        self._run_wrapped(profile, job.id),
                        name=f"cron-{profile}-{job.id}",
                    )

    async def _run_wrapped(self, profile: str, job_id: str) -> None:
        async with self._semaphore:
            try:
                job = CronStore(profile).get(job_id)
                if job and job.enabled:
                    await run_cron_job(job)
            finally:
                self._index.invalidate(profile)


class CronScheduler:
    """Legacy single-profile scheduler; kept for tests and narrow tooling."""

    def __init__(self, profile: str = "default") -> None:
        self.profile = profile
        self._store = CronStore(profile)
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
            if active_runs.is_active(job.id):
                continue
            if job.last_status == "running":
                continue
            if not _job_is_due(job, now=now):
                continue
            async with self._lock:
                if active_runs.is_active(job.id):
                    continue

            asyncio.create_task(self._run_wrapped(job.id), name=f"cron-{job.id}")

    async def _run_wrapped(self, job_id: str) -> None:
        job = self._store.get(job_id)
        if job and job.enabled:
            await run_cron_job(job)