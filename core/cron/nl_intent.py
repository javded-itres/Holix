"""Detect when a chat message asks Holix to schedule a recurring *agent* job.

Implementation requests (build a service/script with its own timer) must NOT
match — those go to the coding agent, not Holix cron auto-create.
"""

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

# User wants Holix gateway cron to run the *agent* on a schedule (digest, remind).
_WANT_HOLIX_SCHEDULE = re.compile(
    r"(?:"
    r"присылай|напомни|напоминай|отправляй\s+мне|шл[ие]\s+мне|"
    r"поставь\s+(?:на\s+)?расписание|запланируй\s+(?:задач|агент|проверк)|"
    r"создай\s+cron|добавь\s+cron|поставь\s+cron|настрой\s+cron|"
    r"/cron\s+add|schedule_cron|holix\s+cron|"
    r"send\s+me\b|remind\s+me\b|schedule\s+(?:this|an?\s+agent|a\s+task)|"
    r"set\s+up\s+(?:a\s+)?(?:cron|recurring)\s+(?:job|task)|"
    r"каждый\s+день\s+(?:присылай|отправляй|шл[ие]|напоминай)|"
    r"every\s+day\s+(?:send|remind|email|notify)"
    r")",
    re.I,
)

# Build/run application code — never auto-create Holix cron for these.
_IMPLEMENTATION = re.compile(
    r"(?:"
    r"\bсоздай\b|\bнапиши\b|\bреализуй\b|\bимплементируй\b|"
    r"консольн\w*\s+сервис|фонов\w*\s+(?:сервис|процесс|job)|"
    r"сервис,?\s+который|скрипт,?\s+который|программ\w*,?\s+которая|"
    r"приложение|daemon|воркер|worker|"
    r"start_background|background_process|"
    r"\bimplement\b|\bwrite\s+a\s+(?:service|script|app|program)\b|"
    r"\bcreate\s+a\s+(?:service|script|app|console)\b|"
    r"long[- ]running|dev\s+server"
    r")",
    re.I,
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
    r"раз\s+в\s+\d+\s+мин(?:ут)?|раз\s+в\s+\d+\s+час(?:а|ов)?|"
    r"в\s+\d{1,2}(?::\d{2})?\s*(?:утра|вечера|часов|ч\.?)|"
    r"по\s+будням|по\s+расписанию"
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
    merged = " ".join(dict.fromkeys(parts))
    return merged


def _strip_schedule_fragments(text: str) -> str:
    task = text
    for pattern in _SCHEDULE_SNIPPETS:
        task = pattern.sub(" ", task)
    task = re.sub(
        r"\b(?:каждый\s+день|ежедневно|раз\s+в\s+день|каждое\s+утро|"
        r"каждый\s+час|ежечасно|каждую\s+неделю|еженедельно|"
        r"раз\s+в\s+\d+\s+мин(?:ут)?|раз\s+в\s+\d+\s+час(?:а|ов)?|"
        r"по\s+будням|по\s+расписанию|"
        r"every\s+day|daily|hourly|weekly|weekdays?)\b",
        " ",
        task,
        flags=re.I,
    )
    task = re.sub(r"\s+", " ", task).strip(" ,.—–-")
    return task.strip()


def detect_cron_intent(text: str) -> CronIntent | None:
    """Return intent only when the user wants Holix to run the agent on a schedule.

    Does **not** match coding tasks such as «создай сервис, который раз в 5 минут…».
    """
    raw = (text or "").strip()
    if len(raw) < 12:
        return None
    if raw.startswith("/"):
        return None
    if _HELP.search(raw):
        return None

    # Implementation / app-building → never Holix cron auto-create
    if _IMPLEMENTATION.search(raw) and not _WANT_HOLIX_SCHEDULE.search(raw):
        return None

    # Require clear intent to schedule Holix agent work (not mere "every N minutes" in a build brief)
    if not _WANT_HOLIX_SCHEDULE.search(raw):
        return None

    if not _RECURRENCE.search(raw):
        return None
    if _ONE_SHOT.search(raw) and not re.search(
        r"каждый|ежеднев|every\s+day|daily|hourly|weekly|every\s+\d+|раз\s+в\s+\d+",
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
