"""Interpret System One JSON for Holix's own gates.

A missing or unreadable answer means "no decision": callers keep the path
they already had. These helpers do not invent a probability.
"""

from __future__ import annotations

from typing import Any

QUALITY_LEVELS: tuple[str, ...] = (
    "The draft misses the request or contradicts the tool results.",
    "The draft is partly relevant but incomplete or unclear.",
    "The draft answers the request and is supported by the available results.",
    "The draft fully answers the request, is clear, and does not claim undone work.",
)

INTERNAL_FLAGS: tuple[str, ...] = ("reflexion", "is_final", "skill_choice", "shell_allow")

DEFAULT_NOUL = 0.8
DEFAULT_CONFIDENCE = 0.6
DEFAULT_QUALITY = 0.7


def question_result(payload: Any, qid: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    direct = payload.get(qid)
    if isinstance(direct, dict):
        return direct
    for wrap in ("answers", "choices", "questions"):
        block = payload.get(wrap)
        if isinstance(block, dict) and isinstance(block.get(qid), dict):
            return block[qid]
    return None


def _confidence_ok(result: dict[str, Any], minimum: float) -> bool:
    if "confidence" not in result:
        return True
    try:
        return float(result["confidence"]) >= minimum
    except (TypeError, ValueError):
        return False


def noul_value(payload: Any, qid: str) -> float | None:
    result = question_result(payload, qid)
    if not result or "noul" not in result:
        return None
    try:
        value = float(result["noul"])
    except (TypeError, ValueError):
        return None
    if value < 0.0 or value > 1.0:
        return None
    return value


def score_index(payload: Any, qid: str, levels: tuple[str, ...] | list[str]) -> int | None:
    result = question_result(payload, qid)
    if not result or "score" not in result:
        return None
    raw = result["score"]
    if isinstance(raw, str):
        for index, level in enumerate(levels):
            if raw.strip() == level:
                return index
        return None
    try:
        index = int(raw)
    except (TypeError, ValueError):
        return None
    if index < 0 or index >= len(levels):
        return None
    return index


def quality_from_score(
    payload: Any,
    *,
    qid: str = "quality",
    levels: tuple[str, ...] = QUALITY_LEVELS,
    quality_threshold: float = DEFAULT_QUALITY,
    confidence_threshold: float = DEFAULT_CONFIDENCE,
) -> tuple[float, bool, str] | None:
    """Map a score position to 0..1. None when the answer cannot be used."""
    result = question_result(payload, qid)
    if result is None or not _confidence_ok(result, confidence_threshold):
        return None
    index = score_index(payload, qid, levels)
    if index is None:
        return None
    span = max(len(levels) - 1, 1)
    quality = index / span
    level = levels[index]
    return quality, quality < quality_threshold, level


def choice_label(
    payload: Any,
    qid: str,
    allowed: set[str],
    *,
    confidence_threshold: float = DEFAULT_CONFIDENCE,
) -> str | None:
    result = question_result(payload, qid)
    if result is None or not _confidence_ok(result, confidence_threshold):
        return None
    label = str(result.get("choice") or "").strip()
    if label not in allowed:
        return None
    return label
