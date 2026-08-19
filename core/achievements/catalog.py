"""Hygiene badges — quality of the skill loop, not volume of creates."""

from __future__ import annotations

from typing import Any

TIER_NAMES = ("Copper", "Silver", "Gold")


def _tiers(*thresholds: int) -> list[dict[str, Any]]:
    return [{"name": name, "threshold": n} for name, n in zip(TIER_NAMES, thresholds, strict=False)]


ACHIEVEMENTS: list[dict[str, Any]] = [
    {
        "id": "first_recipe",
        "name": "First recipe",
        "name_ru": "Первый рецепт",
        "description": "Approve a staged skill so it becomes a live procedure.",
        "description_ru": "Примите черновик skill — он станет живой процедурой.",
        "category": "Skill hygiene",
        "metric": "skills_approved",
        "tiers": _tiers(1),
    },
    {
        "id": "patch_smith",
        "name": "Patch smith",
        "name_ru": "Кузнец патча",
        "description": "Update an existing skill in place instead of minting a new slug.",
        "description_ru": "Обновляйте существующий skill, а не плодите новый slug.",
        "category": "Skill hygiene",
        "metric": "skills_patched",
        "tiers": _tiers(3, 10, 25),
    },
    {
        "id": "skill_returned",
        "name": "The skill returned",
        "name_ru": "Скилл вернулся",
        "description": "Load an approved agent skill in a later session via skill_view.",
        "description_ru": "Откройте approved skill агента в другой сессии через skill_view.",
        "category": "Skill hygiene",
        "metric": "skills_reused",
        "tiers": _tiers(1, 5, 20),
    },
    {
        "id": "learned_it",
        "name": "Learned it",
        "name_ru": "Выучил сам",
        "description": "Approve a skill that came from /learn.",
        "description_ru": "Примите skill, который появился из /learn.",
        "category": "Skill hygiene",
        "metric": "skills_learned_approved",
        "tiers": _tiers(1),
    },
    {
        "id": "clean_refuse",
        "name": "Clean refuse",
        "name_ru": "Чистый отказ",
        "description": "Reject junk or transient-failure drafts instead of keeping them.",
        "description_ru": "Отклоняйте мусор и уроки из тайм-аутов, а не копите их.",
        "category": "Skill hygiene",
        "metric": "skills_refused",
        "tiers": _tiers(5, 15, 40),
    },
    {
        "id": "main_not_flooded",
        "name": "Main stays lean",
        "name_ru": "Main не раздут",
        "description": "Thirty days without auto-assigning approved skills onto main.",
        "description_ru": "30 дней без автоназначения approved skills в main.",
        "category": "Skill hygiene",
        "metric": "days_without_main_assign",
        "secret": True,
        "tiers": _tiers(30),
    },
    {
        "id": "archivist",
        "name": "Archivist",
        "name_ru": "Архивариус",
        "description": "Archive unused agent-created skills instead of leaving them in the index.",
        "description_ru": "Уберите неиспользуемые agent-skills в архив, а не держите их в индексе.",
        "category": "Skill hygiene",
        "metric": "skills_archived",
        "tiers": _tiers(1, 5, 15),
    },
]


def catalog() -> list[dict[str, Any]]:
    return [dict(item) for item in ACHIEVEMENTS]
