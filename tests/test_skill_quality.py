"""Quality score tiers and auto-approve threshold."""

from __future__ import annotations

from pathlib import Path

from core.di.runtime_config import HolixRuntimeConfig
from core.skills.lifecycle import settle_proposal
from core.skills.manager import SkillsManager
from core.skills.proposal import SkillProposalStore
from core.skills.quality import (
    heuristic_quality,
    score_tier,
    should_auto_approve,
)


def test_tiers() -> None:
    assert score_tier(10)["id"] == "found"
    assert score_tier(25)["id"] == "bronze"
    assert score_tier(50)["id"] == "silver"
    assert score_tier(70)["id"] == "gold"
    assert score_tier(90)["id"] == "epic"
    assert should_auto_approve(60)
    assert not should_auto_approve(59)


def test_high_score_auto_approves(tmp_path: Path) -> None:
    mgr = SkillsManager(
        HolixRuntimeConfig.from_settings().with_overrides(
            skills_dir=str(tmp_path / "skills"),
            vector_db_path=str(tmp_path / "vector"),
        )
    )
    store = SkillProposalStore(mgr.skills_dir)
    rec = store.stage(
        name="gold-flow",
        action="create",
        content="## Procedure\n1. do the thing well\n",
        description="Solid reusable recipe",
        quality_score=72,
        locale="en",
    )
    out = settle_proposal(store, rec, manager=mgr, profile="default")
    assert out.get("auto_applied") is True
    assert (mgr.skills_dir / "gold-flow.md").is_file()
    assert store.list_pending() == []


def test_low_score_stays_pending(tmp_path: Path) -> None:
    mgr = SkillsManager(
        HolixRuntimeConfig.from_settings().with_overrides(
            skills_dir=str(tmp_path / "skills"),
            vector_db_path=str(tmp_path / "vector"),
        )
    )
    store = SkillProposalStore(mgr.skills_dir)
    rec = store.stage(
        name="gray-flow",
        action="create",
        content="x",
        description="thin",
        quality_score=18,
    )
    out = settle_proposal(store, rec, manager=mgr, profile="default")
    assert out.get("auto_applied") is False
    assert store.list_pending()
    assert not (mgr.skills_dir / "gray-flow.md").exists()


def test_heuristic_refuse_is_low() -> None:
    assert heuristic_quality({"action": "refuse"}) < 20
