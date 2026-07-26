"""SQLite history of cron job runs (separate from jobs.json)."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.cron.store import cron_dir

_lock = threading.RLock()


def history_db_path(profile: str) -> Path:
    return cron_dir(profile) / "history.db"


def _connect(profile: str) -> sqlite3.Connection:
    path = history_db_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cron_runs (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            profile TEXT NOT NULL,
            job_name TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            duration_s REAL,
            error TEXT,
            result_preview TEXT,
            trigger TEXT NOT NULL DEFAULT 'schedule'
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cron_runs_job ON cron_runs(job_id, started_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cron_runs_started ON cron_runs(started_at DESC)"
    )
    conn.commit()
    return conn


def record_run(
    profile: str,
    *,
    job_id: str,
    job_name: str = "",
    status: str,
    started_at: str | None = None,
    finished_at: str | None = None,
    duration_s: float | None = None,
    error: str | None = None,
    result_preview: str | None = None,
    trigger: str = "schedule",
) -> str:
    """Insert one run row; returns run id."""
    run_id = str(uuid.uuid4())[:16]
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    with _lock:
        conn = _connect(profile)
        try:
            conn.execute(
                """
                INSERT INTO cron_runs (
                    id, job_id, profile, job_name, started_at, finished_at,
                    status, duration_s, error, result_preview, trigger
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    job_id,
                    profile,
                    (job_name or "")[:200],
                    started_at or now,
                    finished_at or now,
                    (status or "unknown")[:40],
                    duration_s,
                    (error or "")[:4000] or None,
                    (result_preview or "")[:4000] or None,
                    (trigger or "schedule")[:40],
                ),
            )
            conn.commit()
        finally:
            conn.close()
    return run_id


def list_runs(
    profile: str,
    *,
    job_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit or 50), 200))
    with _lock:
        conn = _connect(profile)
        try:
            if job_id:
                rows = conn.execute(
                    """
                    SELECT * FROM cron_runs
                    WHERE job_id = ?
                    ORDER BY started_at DESC
                    LIMIT ?
                    """,
                    (job_id, lim),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM cron_runs
                    ORDER BY started_at DESC
                    LIMIT ?
                    """,
                    (lim,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
