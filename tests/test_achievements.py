"""Skill hygiene achievements unlock from approve/patch/refuse, not from create dumps."""

from __future__ import annotations

from pathlib import Path

from core.achievements.engine import AchievementStore, record_skill_signal
from core.di.runtime_config import HolixRuntimeConfig
from core.skills.manager import SkillsManager
from core.skills.proposal import SkillProposalStore


def test_first_recipe_unlocks_on_approve(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    mgr = SkillsManager(
        HolixRuntimeConfig.from_settings().with_overrides(
            skills_dir=str(skills_dir),
            vector_db_path=str(tmp_path / "vector"),
        )
    )
    store = SkillProposalStore(skills_dir)
    rec = store.stage(
        name="approved-flow",
        action="create",
        content="## Procedure\n1. do\n",
        description="A real recipe",
    )
    applied = store.approve(rec["id"], manager=mgr)
    ids = {u["id"] for u in applied.get("unlocks") or []}
    assert "first_recipe" in ids
    snap = AchievementStore(skills_dir).snapshot()
    first = next(a for a in snap["achievements"] if a["id"] == "first_recipe")
    assert first["unlocked"] is True
    assert first["state"] == "unlocked"


def test_refuse_does_not_unlock_first_recipe(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    store = SkillProposalStore(skills_dir)
    rec = store.stage(name="junk-flow", action="create", content="x", description="x")
    store.reject(rec["id"], reason="junk")
    snap = AchievementStore(skills_dir).snapshot()
    first = next(a for a in snap["achievements"] if a["id"] == "first_recipe")
    assert first["unlocked"] is False
    refuse = next(a for a in snap["achievements"] if a["id"] == "clean_refuse")
    assert refuse["progress"] == 1


def test_secret_main_not_shown_until_signal(tmp_path: Path) -> None:
    store = AchievementStore(tmp_path / "skills")
    snap = store.snapshot()
    secret = next(a for a in snap["achievements"] if a["id"] == "main_not_flooded")
    assert secret["state"] == "secret"
    assert secret["name"] == "???"


def test_prompt_index_does_not_list_achievements(tmp_path: Path) -> None:
    mgr = SkillsManager(
        HolixRuntimeConfig.from_settings().with_overrides(
            skills_dir=str(tmp_path / "skills"),
            vector_db_path=str(tmp_path / "vector"),
        )
    )
    mgr.save_skill(name="user-flow", description="d", content="body", origin="agent")
    text = mgr.format_skills_for_prompt(list(mgr.all_skills.values()))
    assert "First recipe" not in text
    assert "first_recipe" not in text
    record_skill_signal(tmp_path / "skills", "approved")
    text2 = mgr.format_skills_for_prompt(list(mgr.all_skills.values()))
    assert "First recipe" not in text2
