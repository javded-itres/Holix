"""Detect short user intents that can bypass the main LLM loop."""

from __future__ import annotations

import re

_SUBAGENT_LIST_RE = re.compile(
    r"(?:"
    r"^/subagents?$|"
    r"^list_subagents\s*\(\s*\)$|"
    r"^список\s+субагентов|"
    r"^покажи\s+субагентов|"
    r"^list\s+subagents$"
    r")",
    re.IGNORECASE,
)

_STATUS_RE = re.compile(
    r"(?:"
    r"^/status$|^статус$|^status$|"
    r"полный\s+статус|"
    r"какой\s+статус|какие\s+задачи|"
    r"что\s+выполняется|"
    r"^покажи\s+статус"
    r")",
    re.IGNORECASE,
)

_WORK_ACTIVITY_RE = re.compile(
    r"(?:"
    r"^что\s+(?:ты\s+)?делаешь|"
    r"^что\s+сейчас\s+делаешь|"
    r"^над\s+чем\s+работаешь|"
    r"^чем\s+занят"
    r")\s*[?.!]*$",
    re.IGNORECASE,
)


def is_subagent_list_request(text: str) -> bool:
    return bool(_SUBAGENT_LIST_RE.match((text or "").strip()))


def is_status_request(text: str) -> bool:
    return bool(_STATUS_RE.search((text or "").strip()))


def is_work_activity_request(text: str) -> bool:
    return bool(_WORK_ACTIVITY_RE.match((text or "").strip()))