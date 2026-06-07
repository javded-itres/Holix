"""Cron expression validation and next-run computation."""

from __future__ import annotations

from datetime import datetime, timezone

from croniter import croniter


def normalize_cron_expression(expr: str) -> str:
    return " ".join((expr or "").strip().split())


def validate_cron_expression(expr: str) -> str:
    """Return normalized expression or raise ValueError."""
    normalized = normalize_cron_expression(expr)
    parts = normalized.split()
    if len(parts) != 5:
        raise ValueError(
            f"Cron must have 5 fields (minute hour day month weekday), got {len(parts)}: {expr!r}"
        )
    try:
        croniter(normalized, datetime.now(timezone.utc))
    except Exception as e:
        raise ValueError(f"Invalid cron expression: {e}") from e
    return normalized


def compute_next_run(expr: str, *, base: datetime | None = None) -> datetime:
    """Next run time (UTC) after base."""
    normalized = validate_cron_expression(expr)
    ref = base or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    itr = croniter(normalized, ref)
    nxt = itr.get_next(datetime)
    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=timezone.utc)
    return nxt


def format_next_run_iso(expr: str, *, base: datetime | None = None) -> str:
    return compute_next_run(expr, base=base).isoformat()