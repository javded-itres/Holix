"""skill_view / skill_manage / learn staging."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.di.runtime_config import HolixRuntimeConfig
from core.skills.learn import learn_turn_prompt, stage_learn_proposal
from core.skills.manager import SkillsManager
from core.tools.skills import SkillManageTool, SkillViewTool


def _mgr(tmp_path: Path) -> SkillsManager:
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        skills_dir=str(tmp_path / "skills"),
        vector_db_path=str(tmp_path / "vector"),
    )
    return SkillsManager(cfg)


def test_format_skills_prompt_is_index_unless_bundled(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    mgr.save_skill(
        name="user-flow",
        description="A learned flow",
        content="## Procedure\nSECRET_BODY_SHOULD_NOT_INLINE\n",
        origin="agent",
    )
    formatted = mgr.format_skills_for_prompt(list(mgr.all_skills.values()))
    assert "user-flow" in formatted
    assert "A learned flow" in formatted
    assert "SECRET_BODY_SHOULD_NOT_INLINE" not in formatted
    assert "skill_view" in formatted


def test_format_skills_prompt_never_inlines_bundled(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    mgr.save_skill(
        name="holix-bundled-demo",
        description="Bundled workflow",
        content="## Procedure\nBUNDLED_BODY_MUST_STAY_OUT\n",
        origin="bundled",
    )
    formatted = mgr.format_skills_for_prompt(list(mgr.all_skills.values()))
    assert "holix-bundled-demo" in formatted
    assert "BUNDLED_BODY_MUST_STAY_OUT" not in formatted
    dumped = mgr.format_skills_for_prompt(list(mgr.all_skills.values()), include_body=True)
    assert "BUNDLED_BODY_MUST_STAY_OUT" in dumped


def test_skills_prompt_block_suggests_without_bodies(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    mgr.save_skill(
        name="alpha-skill",
        description="Alpha flow",
        content="ALPHA_SECRET_BODY",
        origin="agent",
    )
    mgr.save_skill(
        name="beta-skill",
        description="Beta flow",
        content="BETA_SECRET_BODY",
        origin="bundled",
    )
    block = mgr.skills_prompt_block("alpha", agent_slot="main")
    assert "`alpha-skill`" in block
    assert "`beta-skill`" in block
    assert "ALPHA_SECRET_BODY" not in block
    assert "BETA_SECRET_BODY" not in block
    assert "skill_view" in block


def test_skills_prompt_block_truncates_catalog(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    for i in range(4):
        mgr.save_skill(
            name=f"skill-{i}",
            description=f"desc {i}",
            content=f"BODY{i}",
            origin="agent",
        )
    block = mgr.skills_prompt_block("", agent_slot="main", cap=2)
    assert "truncated" in block.lower()
    listed = sum(1 for i in range(4) if f"`skill-{i}`" in block)
    assert listed == 2
    assert "BODY0" not in block


@pytest.mark.asyncio
async def test_skill_view_and_manage_stage(tmp_path: Path, monkeypatch) -> None:
    mgr = _mgr(tmp_path)
    mgr.save_skill(
        name="demo-flow",
        description="Demo",
        content="## Procedure\n1. do it\n",
        origin="agent",
    )
    monkeypatch.setattr("core.tools.skills._skills_manager", lambda: mgr)

    viewed = await SkillViewTool().execute(name="demo-flow")
    assert "## Procedure" in viewed
    listed = await SkillViewTool().execute()
    assert "demo-flow" in listed

    staged = await SkillManageTool().execute(
        action="create",
        name="new-from-tool",
        description="From tool",
        content="## When to Use\nx\n\n## Procedure\n1. y\n",
    )
    assert "Staged create" in staged
    assert not (mgr.skills_dir / "new-from-tool.md").exists()
    assert (mgr.skills_dir / "_pending").is_dir()


def test_learn_stages_from_text(tmp_path: Path) -> None:
    rec = stage_learn_proposal(
        tmp_path / "skills",
        hint="deploy staging",
        text="1. build\n2. rsync\n3. healthcheck",
    )
    assert rec["status"] == "pending"
    assert rec["origin"] == "learn"
    assert "healthcheck" in rec["content"]
    assert "When to Use" in rec["content"]
    assert "skill_manage" in learn_turn_prompt("this conversation")


def test_learn_url_rejects_localhost() -> None:
    from core.skills.learn import _read_url

    with pytest.raises(ValueError):
        _read_url("http://127.0.0.1/secret")
    with pytest.raises(ValueError):
        _read_url("file:///etc/passwd")
