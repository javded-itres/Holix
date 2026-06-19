"""Detect recurring-task intent in natural-language chat messages."""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.cron.schedule_parse import (
    _AT_TIME,
    _DAILY,
    _EVERY_HOURS,
    _EVERY_MINUTES,
    _HOURLY,
    _RU_AT_TIME,
    _RU_DAILY,
    _RU_EVERY_HOURS,
    _RU_EVERY_MINUTES,
    _RU_HOURLY,
    _RU_WEEKDAY,
    _RU_WEEKLY,
    _WEEKDAY,
    _WEEKLY,
    parse_schedule_to_cron,
)

_RECURRENCE = re.compile(
    r"(?:"
    r"every\s+day|daily|every\s+hour|hourly|every\s+week|weekly|weekdays?|"
    r"every\s+\d+\s+min(?:ute)?s?|every\s+\d+\s+hours?|"
    r"(?:at|@)\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)?|"
    r"каждый\s+день|ежедневно|раз\s+в\s+день|каждое\s+утро|"
    r"каждый\s+час|ежечасно|раз\s+в\s+час|"
    r"каждую\s+неделю|еженедельно|раз\s+в\s+неделю|"
    r"каждые\s+\d+\s+мин(?:ут)?|каждые\s+\d+\s+час(?:а|ов)?|"
    r"в\s+\d{1,2}(?::\d{2})?\s*(?:утра|вечера|часов|ч\.?)?|"
    r"по\s+будням|по\s+расписанию|регулярно|периодически"
    r")",
    re.I,
)

_ONE_SHOT = re.compile(
    r"(?:"
    r"\bодин\s+раз\b|\bсейчас\b|\bпрямо\s+сейчас\b|\bjust\s+once\b|\bonce\b(?!\s+a\s+day)"
    r")",
    re.I,
)

_HELP = re.compile(
    r"(?:"
    r"^как\s+(?:настроить|работает|использовать)|"
    r"^что\s+такое\s+cron|"
    r"^how\s+(?:does|to)\s+(?:cron|schedule)|"
    r"^explain\s+cron|"
    r"^/cron\b"
    r")",
    re.I,
)

_SCHEDULE_SNIPPETS: tuple[re.Pattern[str], ...] = (
    _EVERY_MINUTES,
    _RU_EVERY_MINUTES,
    _EVERY_HOURS,
    _RU_EVERY_HOURS,
    _HOURLY,
    _RU_HOURLY,
    _WEEKLY,
    _RU_WEEKLY,
    _WEEKDAY,
    _RU_WEEKDAY,
    _DAILY,
    _RU_DAILY,
    _AT_TIME,
    _RU_AT_TIME,
)


@dataclass(frozen=True)
class CronIntent:
    """Parsed natural-language cron request."""

    schedule: str
    task: str
    cron_expression: str


def _schedule_phrase(text: str) -> str | None:
    """Build a schedule substring suitable for ``parse_schedule_to_cron``."""
    low = text.lower()
    parts: list[str] = []
    for pattern in _SCHEDULE_SNIPPETS:
        m = pattern.search(low)
        if m:
            parts.append(m.group(0).strip())
    if not parts:
        if _RECURRENCE.search(text):
            if re.search(r"каждый\s+день|ежедневно|every\s+day|daily", low, re.I):
                return "every day at 9"
            if re.search(r"каждый\s+час|hourly|every\s+hour", low, re.I):
                return "hourly"
        return None
    # Prefer daily+time combo when both present
    merged = " ".join(dict.fromkeys(parts))
    return merged


def _strip_schedule_fragments(text: str) -> str:
    task = text
    for pattern in _SCHEDULE_SNIPPETS:
        task = pattern.sub(" ", task)
    task = re.sub(
        r"\b(?:каждый\s+день|ежедневно|раз\s+в\s+день|каждое\s+утро|"
        r"каждый\s+час|ежечасно|каждую\s+неделю|еженедельно|"
        r"по\s+будням|по\s+расписанию|регулярно|периодически|"
        r"every\s+day|daily|hourly|weekly|weekdays?)\b",
        " ",
        task,
        flags=re.I,
    )
    task = re.sub(r"\s+", " ", task).strip(" ,.—–-")
    return task.strip()


def detect_cron_intent(text: str) -> CronIntent | None:
    """Return cron intent when the message asks for a recurring scheduled task."""
    raw = (text or "").strip()
    if len(raw) < 12:
        return None
    if raw.startswith("/"):
        return None
    if _HELP.search(raw):
        return None
    if not _RECURRENCE.search(raw):
        return None
    if _ONE_SHOT.search(raw) and not re.search(
        r"каждый|ежеднев|every\s+day|daily|hourly|weekly|every\s+\d+",
        raw,
        re.I,
    ):
        return None

    schedule = _schedule_phrase(raw)
    if not schedule:
        return None

    try:
        cron_expression = parse_schedule_to_cron(schedule)
    except ValueError:
        return None

    task = _strip_schedule_fragments(raw)
    if len(task) < 8:
        return None

    return CronIntent(schedule=schedule, task=task, cron_expression=cron_expression)