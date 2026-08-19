"""Detect near-duplicate / junk skills so sessions do not flood the profile."""

from __future__ import annotations

import re
from typing import Any

from core.hub.normalize import slugify_skill_name

_STOP = frozenset(
    {
        "and",
        "the",
        "for",
        "with",
        "from",
        "into",
        "via",
        "to",
        "a",
        "an",
        "of",
        "in",
        "on",
        "or",
        "by",
        "at",
        "as",
        "after",
        "before",
    }
)

_TRIVIAL_USER = re.compile(
    r"^(привет|здравствуй|hello|hi+|hey|ok|ок|да|нет|спасибо|thanks|ping|пон|"
    r"как дела|что ты умеешь|status|статус|ты тут|you there)\b",
    re.I,
)

_TRIVIAL_TAGS = frozenset(
    {
        "persona",
        "greeting",
        "status",
        "ping",
        "format",
        "smalltalk",
        "chitchat",
    }
)


def _stem_token(tok: str) -> str:
    aliases = {
        "recalculator": "recalc",
        "recalculation": "recalc",
        "generator": "gen",
        "generation": "gen",
        "orchestrator": "orch",
        "orchestration": "orch",
        "builder": "build",
        "scaffolding": "scaffold",
        "delegation": "delegate",
        "delegator": "delegate",
    }
    if tok in aliases:
        return aliases[tok]
    for suf in ("ation", "ations", "ings", "ing", "ers", "er", "ors"):
        if len(tok) > len(suf) + 3 and tok.endswith(suf):
            return tok[: -len(suf)]
    return tok


def skill_tokens(text: str) -> set[str]:
    raw = slugify_skill_name(text or "")
    raw = raw.replace("sub-agent", "subagent")
    out: set[str] = set()
    for tok in raw.split("-"):
        if len(tok) <= 2 or tok in _STOP:
            continue
        out.add(_stem_token(tok))
    return out


def names_are_near_duplicate(left: str, right: str) -> bool:
    a = slugify_skill_name(left)
    b = slugify_skill_name(right)
    if not a or not b:
        return False
    if a == b:
        return True
    ta, tb = skill_tokens(a), skill_tokens(b)
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    union = len(ta | tb)
    if inter >= 3 and union and inter / union >= 0.6:
        return True
    if inter >= 2 and (ta <= tb or tb <= ta):
        return True
    return False


def descriptions_are_near_duplicate(left: str, right: str) -> bool:
    ta, tb = skill_tokens(left), skill_tokens(right)
    if len(ta) < 4 or len(tb) < 4:
        return False
    union = len(ta | tb)
    return bool(union) and len(ta & tb) / union >= 0.55


def find_duplicate_skill(
    existing: dict[str, dict[str, Any]] | list[dict[str, Any]],
    *,
    name: str,
    description: str = "",
) -> dict[str, Any] | None:
    """Return an already-loaded skill that this new one would duplicate."""
    if isinstance(existing, dict):
        rows = list(existing.values())
    else:
        rows = list(existing)
    want = slugify_skill_name(name)
    for skill in rows:
        other = str(skill.get("name") or "")
        if not other:
            continue
        if names_are_near_duplicate(want, other):
            return skill
        if description and descriptions_are_near_duplicate(
            description, str(skill.get("description") or "")
        ):
            return skill
    return None


def is_trivial_session(messages: list[dict[str, Any]], final_result: str) -> bool:
    """True for greetings / status pings that must not become skills."""
    users = [
        str(m.get("content") or "").strip()
        for m in messages
        if m.get("role") == "user" and str(m.get("content") or "").strip()
    ]
    if not users:
        return True
    first = users[0]
    if len(first) < 12 or _TRIVIAL_USER.search(first):
        return True
    if len(users) == 1 and len(first.split()) <= 3:
        return True
    text = (final_result or "").strip()
    if text and len(text) < 24 and len(first) < 24:
        return True
    return False


_TRANSIENT = re.compile(
    r"\b(timeout|timed out|429|rate.?limit|econnreset|connection reset|"
    r"temporarily unavailable|try again later|таймаут|не ответил|"
    r"сеть недоступ|connection refused)\b",
    re.I,
)
_AVOID_TOOL = re.compile(
    r"\b(do not (use|call|retry)|avoid (using|calling|the tool)|"
    r"больше не (звать|вызывать|использовать)|не использовать этот (тул|инструмент)|"
    r"never (call|use) (this )?(tool|mcp))\b",
    re.I,
)


def is_transient_failure_lesson(
    messages: list[dict[str, Any]],
    final_result: str,
) -> bool:
    """True when the only lesson is 'avoid this tool' after a transient error."""
    parts: list[str] = [final_result or ""]
    for msg in messages:
        if msg.get("role") in {"assistant", "tool"}:
            parts.append(str(msg.get("content") or ""))
    blob = "\n".join(parts)
    if not _TRANSIENT.search(blob):
        return False
    if _AVOID_TOOL.search(blob):
        return True
    # Error-only wrap-up with no recovered successful workflow.
    result = (final_result or "").lower()
    if "error" in result and not any(
        tok in result for tok in ("fixed", "resolved", "done", "готово", "исправ")
    ):
        return True
    return False


def looks_like_junk_skill(
    *, name: str, description: str = "", tags: list[str] | None = None
) -> bool:
    slug = slugify_skill_name(name)
    tokens = skill_tokens(slug + " " + (description or ""))
    if tokens & _TRIVIAL_TAGS and len(tokens) <= 5:
        return True
    tagset = {slugify_skill_name(t) for t in (tags or [])}
    if tagset & _TRIVIAL_TAGS and len(tokens) <= 6:
        return True
    return False
