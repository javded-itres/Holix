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


# User is criticizing *this agent*, not asking to debug their own code.
_SELF_DIAGNOSE_RE = re.compile(
    r"(?is)"
    r"("
    r"проверь\s+себя"
    r"|проверь\s+свою\s+работ"
    r"|проверь\s+эту\s+сессию"
    r"|самодиагност"
    r"|почему\s+ты\s+(делаешь|отвеча|работаешь|так\s+делаешь|вр[её]шь)"
    r"|ты\s+(делаешь|сделал[аи]?)\s+не\s+так"
    r"|ты\s+отвечаешь\s+неправильно"
    r"|ты\s+ответил[аи]?\s+неправильно"
    r"|ты\s+не\s*прав\b"
    r"|ты\s+ошиб(ся|лась|ился)"
    r"|разберись\s+почему\s+ты"
    r"|что\s+у\s+тебя\s+пошло\s+не\s+так"
    r"|проанализируй\s+(свою\s+)?сессию"
    r"|посмотри\s+что\s+ты\s+(сделал|делаешь)\s+не\s+так"
    r"|check\s+yourself"
    r"|diagnose\s+(yourself|this\s+session)"
    r"|self[- ]diagnos"
    r"|why\s+are\s+you\s+(doing\s+(it|this)\s+wrong|answering\s+wrong)"
    r"|you(?:'re|\s+are)\s+(answering\s+incorrectly|doing\s+it\s+wrong)"
    r"|you(?:'re|\s+are)\s+wrong"
    r"|that(?:'s|\s+is)\s+the\s+wrong\s+answer"
    r")"
)


def is_self_diagnose_request(text: str) -> bool:
    """True when the user asks Holix to inspect its own session / mistakes."""
    raw = (text or "").strip()
    if not raw or len(raw) > 400:
        return False
    return bool(_SELF_DIAGNOSE_RE.search(raw))
