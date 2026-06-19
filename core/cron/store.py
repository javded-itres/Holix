"""Persist cron jobs under ~/.holix/profiles/<profile>/data/cron/."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from cli.core import ProfileManager

from core.cron.expressions import format_next_run_iso, validate_cron_expression
from core.cron.models import CronJob, CronJobStore


def cron_dir(profile: str) -> Path:
    from core.profile.names import validate_profile_name

    d = ProfileManager().get_profile_dir(validate_profile_name(profile)) / "data" / "cron"
    d.mkdir(parents=True, exist_ok=True)
    return d


def jobs_path(profile: str) -> Path:
    return cron_dir(profile) / "jobs.json"


def runs_log_path(profile: str) -> Path:
    return cron_dir(profile) / "runs.log"


class CronStore:
    def __init__(self, profile: str = "default") -> None:
        from core.profile.names import validate_profile_name

        self.profile = validate_profile_name(profile)
        self._path = jobs_path(profile)

    def load(self) -> CronJobStore:
        if not self._path.exists():
            return CronJobStore()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return CronJobStore.model_validate(data)
        except Exception:
            return CronJobStore()

    def save(self, store: CronJobStore) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            store.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def list_jobs(self, *, enabled_only: bool = False) -> list[CronJob]:
        jobs = self.load().jobs
        if enabled_only:
            jobs = [j for j in jobs if j.enabled]
        return sorted(jobs, key=lambda j: j.name.lower())

    def get(self, job_id: str) -> CronJob | None:
        for j in self.load().jobs:
            if j.id == job_id:
                return j
        return None

    def _touch_next_run(self, job: CronJob) -> None:
        if job.enabled:
            try:
                job.next_run_at = format_next_run_iso(job.cron_expression)
            except ValueError:
                job.next_run_at = None
        else:
            job.next_run_at = None

    def add(
        self,
        *,
        task: str,
        cron_expression: str,
        name: str = "",
        enabled: bool = True,
        notify_chat_id: int | None = None,
        notify_max_user_id: int | None = None,
        notify_max_chat_id: int | None = None,
        session_id: str | None = None,
        skills: list[str] | None = None,
        model_override: str | None = None,
    ) -> CronJob:
        task = (task or "").strip()
        if not task:
            raise ValueError("Task text is required")
        expr = validate_cron_expression(cron_expression)
        store = self.load()
        job = CronJob(
            name=(name or "").strip() or task[:48],
            task=task,
            cron_expression=expr,
            enabled=enabled,
            profile=self.profile,
            notify_chat_id=notify_chat_id,
            notify_max_user_id=notify_max_user_id,
            notify_max_chat_id=notify_max_chat_id,
            session_id=(session_id or "").strip() or None,
            skills=list(skills or []),
            model_override=(model_override or "").strip() or None,
        )
        self._touch_next_run(job)
        store.jobs.append(job)
        self.save(store)
        return job

    def update(self, job: CronJob) -> CronJob:
        store = self.load()
        job.updated_at = datetime.now(UTC).isoformat()
        self._touch_next_run(job)
        for i, j in enumerate(store.jobs):
            if j.id == job.id:
                store.jobs[i] = job
                self.save(store)
                return job
        raise KeyError(job.id)

    def set_enabled(self, job_id: str, enabled: bool) -> CronJob:
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        job.enabled = enabled
        return self.update(job)

    def remove(self, job_id: str) -> bool:
        store = self.load()
        before = len(store.jobs)
        store.jobs = [j for j in store.jobs if j.id != job_id]
        if len(store.jobs) == before:
            return False
        self.save(store)
        return True

    def refresh_all_next_runs(self) -> None:
        store = self.load()
        for job in store.jobs:
            self._touch_next_run(job)
        self.save(store)