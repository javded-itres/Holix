"""Skill quality score (1–100) and visual tiers."""

from __future__ import annotations

from typing import Any

AUTO_APPROVE_SCORE = 60

# Inclusive lower bound, exclusive upper bound except the last tier.
TIERS: tuple[dict[str, Any], ...] = (
    {
        "id": "found",
        "min": 1,
        "max": 20,
        "color": "gray",
        "label_en": "Gray",
        "label_ru": "Серый",
        "hint_en": "Skill found",
        "hint_ru": "Скилл найден",
    },
    {
        "id": "bronze",
        "min": 20,
        "max": 40,
        "color": "bronze",
        "label_en": "Bronze",
        "label_ru": "Бронза",
        "hint_en": "Can approve, not required",
        "hint_ru": "Можно апрувнуть, не обязательно",
    },
    {
        "id": "silver",
        "min": 40,
        "max": 60,
        "color": "silver",
        "label_en": "Silver",
        "label_ru": "Серебро",
        "hint_en": "Safe to approve",
        "hint_ru": "Уже можно точно апрувнуть",
    },
    {
        "id": "gold",
        "min": 60,
        "max": 80,
        "color": "gold",
        "label_en": "Gold",
        "label_ru": "Золото",
        "hint_en": "Auto-accepted",
        "hint_ru": "Автопринятие",
    },
    {
        "id": "epic",
        "min": 80,
        "max": 101,
        "color": "epic",
        "label_en": "Epic",
        "label_ru": "Эпический",
        "hint_en": "Definitely auto-accepted",
        "hint_ru": "Точно автопринятие",
    },
)


def clamp_score(value: Any) -> int:
    try:
        score = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, score))


def score_tier(score: int) -> dict[str, Any]:
    n = clamp_score(score)
    if n <= 0:
        return {
            "id": "none",
            "min": 0,
            "max": 1,
            "color": "gray",
            "label_en": "—",
            "label_ru": "—",
            "hint_en": "No score",
            "hint_ru": "Нет оценки",
            "score": 0,
        }
    for tier in TIERS:
        if tier["min"] <= n < tier["max"]:
            return {**tier, "score": n}
    return {**TIERS[-1], "score": n}


def should_auto_approve(score: int) -> bool:
    return clamp_score(score) >= AUTO_APPROVE_SCORE


def heuristic_quality(skill_data: dict[str, Any]) -> int:
    """Fallback when the model omitted QUALITY_SCORE."""
    if str(skill_data.get("action") or "").lower() == "refuse":
        return 8
    score = 18
    if (skill_data.get("when_to_use") or "").strip():
        score += 14
    procedure = (skill_data.get("procedure") or skill_data.get("content") or "").strip()
    if len(procedure) >= 80:
        score += 18
    elif procedure:
        score += 8
    if (skill_data.get("pitfalls") or "").strip():
        score += 14
    if (skill_data.get("verification") or "").strip():
        score += 14
    if skill_data.get("examples"):
        score += 8
    desc = (skill_data.get("description") or "").strip()
    if 12 <= len(desc) <= 120:
        score += 6
    return clamp_score(score)
