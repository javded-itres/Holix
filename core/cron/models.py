"""Cron job data models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class CronJob(BaseModel):
    """Scheduled agent task (standard 5-field cron)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str = ""
    task: str
    cron_expression: str
    enabled: bool = True
    profile: str = "default"
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    last_run_at: str | None = None
    last_status: str | None = None  # success | error | running | skipped
    last_error: str | None = None
    last_duration_s: float | None = None
    next_run_at: str | None = None
    run_count: int = 0
    notify_chat_id: int | None = None  # Telegram chat ID for notifications
    notify_max_user_id: int | None = None
    notify_max_chat_id: int | None = None
    session_id: str | None = None  # Session that receives run summaries (e.g. tui_default)
    last_result: str | None = None  # Truncated assistant output from the last run
    skills: list[str] = Field(default_factory=list)
    model_override: str | None = None

    def conversation_id(self) -> str:
        """Dedicated conversation for the full cron run log."""
        return f"cron-{self.id}"


class CronJobStore(BaseModel):
    version: int = 1
    jobs: list[CronJob] = Field(default_factory=list)