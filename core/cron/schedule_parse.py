"""Parse user schedule strings into cron expressions."""

from __future__ import annotations

import re

from core.cron.expressions import validate_cron_expression

# Strict 5-field cron (reject English phrases like "every day at 10 am")
_CRON_FIELD = re.compile(r"^[\d*/,\-A-Za-z#?]+$")
_CRON_BANNED_TOKENS = frozenset(
    {
        "every",
        "day",
        "at",
        "am",
        "pm",
        "hour",
        "hours",
        "minute",
        "minutes",
        "daily",
        "weekly",
        "hourly",
        "weekdays",
        "каждый",
        "каждую",
        "каждые",
        "день",
        "час",
        "часов",
        "минут",
        "утра",
        "вечера",
        "ежедневно",
        "еженедельно",
    }
)

# English
_EVERY_MINUTES = re.compile(r"every\s+(\d+)\s+min", re.I)
_EVERY_HOURS = re.compile(r"every\s+(\d+)\s+hour", re.I)
_AT_TIME = re.compile(r"(?:at|@)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.I)
_DAILY = re.compile(r"every\s+day|daily", re.I)
_HOURLY = re.compile(r"every\s+hour|hourly", re.I)
_WEEKLY = re.compile(r"every\s+week|weekly", re.I)
_WEEKDAY = re.compile(r"weekdays?|mon-fri", re.I)

# Russian
_RU_EVERY_MINUTES = re.compile(r"каждые\s+(\d+)\s+мин", re.I)
_RU_EVERY_HOURS = re.compile(r"каждые\s+(\d+)\s+час", re.I)
_RU_DAILY = re.compile(r"каждый\s+день|ежедневно|раз\s+в\s+день|каждое\s+утро", re.I)
_RU_HOURLY = re.compile(r"каждый\s+час|ежечасно|раз\s+в\s+час", re.I)
_RU_WEEKLY = re.compile(r"каждую\s+неделю|еженедельно|раз\s+в\s+неделю", re.I)
_RU_WEEKDAY = re.compile(r"по\s+будням|будни", re.I)
_RU_AT_TIME = re.compile(
    r"в\s+(\d{1,2})(?::(\d{2}))?\s*(утра|вечера|часов|ч\.?)?",
    re.I,
)


def _looks_like_five_field_cron(raw: str) -> bool:
    parts = raw.strip().split()
    if len(parts) != 5:
        return False
    for part in parts:
        low = part.lower()
        if low in _CRON_BANNED_TOKENS:
            return False
        if not _CRON_FIELD.match(part):
            return False
    return True


def _hour_minute_from_match(
    hour_s: str,
    minute_s: str | None,
    *,
    ampm: str | None = None,
    day_part: str | None = None,
) -> tuple[int, int]:
    hour = int(hour_s)
    minute = int(minute_s or 0)
    suffix = (ampm or "").lower()
    if suffix == "pm" and hour < 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    part = (day_part or "").lower()
    if part == "вечера" and 1 <= hour <= 11:
        hour += 12
    if part == "утра" and hour == 12:
        hour = 0
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("Invalid time in schedule")
    return hour, minute


def parse_schedule_to_cron(schedule: str) -> str:
    """Convert natural-ish schedule or raw cron to validated 5-field cron."""
    raw = (schedule or "").strip()
    if not raw:
        raise ValueError("Schedule is empty")

    if _looks_like_five_field_cron(raw):
        return validate_cron_expression(raw)

    low = raw.lower()

    for pattern in (_EVERY_MINUTES, _RU_EVERY_MINUTES):
        m = pattern.search(low)
        if m:
            n = int(m.group(1))
            if n < 1 or n > 59:
                raise ValueError("Minutes interval must be 1–59")
            return validate_cron_expression(f"*/{n} * * * *")

    for pattern in (_EVERY_HOURS, _RU_EVERY_HOURS):
        m = pattern.search(low)
        if m:
            n = int(m.group(1))
            if n < 1 or n > 23:
                raise ValueError("Hours interval must be 1–23")
            return validate_cron_expression(f"0 */{n} * * *")

    if _HOURLY.search(low) or _RU_HOURLY.search(low):
        return validate_cron_expression("0 * * * *")

    if _WEEKLY.search(low) or _RU_WEEKLY.search(low):
        return validate_cron_expression("0 9 * * 1")

    if _WEEKDAY.search(low) or _RU_WEEKDAY.search(low):
        return validate_cron_expression("0 9 * * 1-5")

    daily = _DAILY.search(low) or _RU_DAILY.search(low)
    at_en = _AT_TIME.search(low)
    at_ru = _RU_AT_TIME.search(low)
    if daily or at_en or at_ru:
        hour, minute = 9, 0
        if at_en:
            hour, minute = _hour_minute_from_match(
                at_en.group(1),
                at_en.group(2),
                ampm=at_en.group(3),
            )
        elif at_ru:
            hour, minute = _hour_minute_from_match(
                at_ru.group(1),
                at_ru.group(2),
                day_part=at_ru.group(3),
            )
        return validate_cron_expression(f"{minute} {hour} * * *")

    raise ValueError(
        "Could not parse schedule. Use 5-field cron (e.g. `0 9 * * *`) or phrases like "
        "`every day at 9:00`, `каждый день в 10 утра`, `every 30 minutes`, `hourly`."
    )