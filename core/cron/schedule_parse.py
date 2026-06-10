"""Parse user schedule strings into cron expressions."""

from __future__ import annotations

import re

from core.cron.expressions import validate_cron_expression

# Already 5-field cron
_CRON_RE = re.compile(
    r"^(\S+\s+\S+\s+\S+\s+\S+\s+\S+)$"
)

# every N minutes
_EVERY_MINUTES = re.compile(r"every\s+(\d+)\s+min", re.I)
_EVERY_HOURS = re.compile(r"every\s+(\d+)\s+hour", re.I)
_AT_TIME = re.compile(r"(?:at|@)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.I)
_DAILY = re.compile(r"every\s+day|daily", re.I)
_HOURLY = re.compile(r"every\s+hour|hourly", re.I)
_WEEKLY = re.compile(r"every\s+week|weekly", re.I)
_WEEKDAY = re.compile(r"weekdays?|mon-fri", re.I)


def parse_schedule_to_cron(schedule: str) -> str:
    """Convert natural-ish schedule or raw cron to validated 5-field cron."""
    raw = (schedule or "").strip()
    if not raw:
        raise ValueError("Schedule is empty")

    if _CRON_RE.match(raw):
        return validate_cron_expression(raw)

    low = raw.lower()

    m = _EVERY_MINUTES.search(low)
    if m:
        n = int(m.group(1))
        if n < 1 or n > 59:
            raise ValueError("Minutes interval must be 1–59")
        return validate_cron_expression(f"*/{n} * * * *")

    m = _EVERY_HOURS.search(low)
    if m:
        n = int(m.group(1))
        if n < 1 or n > 23:
            raise ValueError("Hours interval must be 1–23")
        return validate_cron_expression(f"0 */{n} * * *")

    if _HOURLY.search(low):
        return validate_cron_expression("0 * * * *")

    if _WEEKLY.search(low):
        return validate_cron_expression("0 9 * * 1")

    if _WEEKDAY.search(low):
        return validate_cron_expression("0 9 * * 1-5")

    if _DAILY.search(low) or _AT_TIME.search(low):
        m = _AT_TIME.search(low)
        hour, minute = 9, 0
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2) or 0)
            ampm = (m.group(3) or "").lower()
            if ampm == "pm" and hour < 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("Invalid time in schedule")
        return validate_cron_expression(f"{minute} {hour} * * *")

    raise ValueError(
        "Could not parse schedule. Use 5-field cron (e.g. `0 9 * * *`) or phrases like "
        "`every day at 9:00`, `every 30 minutes`, `hourly`."
    )