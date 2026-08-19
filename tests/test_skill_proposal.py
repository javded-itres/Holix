"""Auto-skills stage to _pending and do not write live files or assignments."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.di.runtime_config import HolixRuntimeConfig
from core.skills.dedup import is_transient_failure_lesson
from core.skills.generator import SkillGenerator
from core.skills.manager import SkillsManager
from core.skills.proposal import SkillProposalStore
from core.skills.self_improve import (
    maybe_propose_skill,
    maybe_propose_skill_from_subagent,
)


def _mgr(tmp_path: Path) -> SkillsManager:
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        skills_dir=str(tmp_path / "skills"),
        vector_db_path=str(tmp_path / "vector"),
    )
    return SkillsManager(cfg)


def test_transient_failure_lesson_detected() -> None:
    assert is_transient_failure_lesson(
        [
            {"role": "user", "content": "call context7"},
            {"role": "tool", "content": "Error: timed out after 30s"},
            {
                "role": "assistant",
                "content": "Context7 timed out. Do not call this tool again.",
            },
        ],
        "Do not call this tool again after the timeout.",
    )
    assert not is_transient_failure_lesson(
        [
            {"role": "user", "content": "Add FastAPI CRUD with Dishka"},
            {"role": "assistant", "content": "Created app/main.py and tests passed."},
        ],
        "Готово: CRUD и pytest зелёный.",
    )


def test_stage_does_not_write_live_skill(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    store = SkillProposalStore(mgr.skills_dir)
    rec = store.stage(
        name="fastapi-crud",
        action="create",
        content="## Procedure\n1. write routes\n",
        description="FastAPI CRUD",
        tags=["fastapi"],
    )
    assert rec["status"] == "pending"
    assert rec["id"].startswith("psp-")
    with pytest.raises(ValueError, match="invalid proposal id"):
        store._dir("../psp-escape")
    assert store.get("psp-not-a-real-id") is None
    assert not (mgr.skills_dir / "fastapi-crud.md").exists()
    assert store._skill_path(rec["id"]).is_file()
    listed = store.list_pending()
    assert len(listed) == 1
    assert listed[0]["name"] == "fastapi-crud"


def test_approve_create_without_assign(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    store = SkillProposalStore(mgr.skills_dir)
    rec = store.stage(
        name="new-flow",
        action="create",
        content="## When to Use\nwhen doing X\n",
        description="Do X",
    )
    applied = store.approve(rec["id"], manager=mgr, assign_to=None)
    assert applied["status"] == "approved"
    assert (mgr.skills_dir / "new-flow.md").is_file()
    assert "new-flow" not in (mgr.skill_assignments.get("main") or [])
    assert store.list_pending() == []


def test_approve_patches_existing(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    first = mgr.save_skill(
        name="fastapi-dishka-catalog-service",
        description="Build FastAPI catalog services with Dishka DI",
        content="v1",
        tags=["fastapi"],
    )
    store = SkillProposalStore(mgr.skills_dir)
    rec = store.stage(
        name="fastapi-dishka-sqlite-catalog",
        action="patch",
        target_name="fastapi-dishka-catalog-service",
        content="v2 patched",
        description="Build FastAPI catalog services with Dishka DI",
    )
    applied = store.approve(rec["id"], manager=mgr)
    assert applied["action"] == "patch"
    assert Path(applied["filepath"]).resolve() == first.resolve()
    assert "v2 patched" in first.read_text(encoding="utf-8")
    assert not (mgr.skills_dir / "fastapi-dishka-sqlite-catalog.md").exists()


def test_reject_drops_proposal(tmp_path: Path) -> None:
    store = SkillProposalStore(tmp_path / "skills")
    rec = store.stage(name="junk-flow", action="create", content="x", description="x")
    store.reject(rec["id"], reason="nope")
    assert store.list_pending() == []
    assert store.get(rec["id"]) is None


def test_generator_parses_action_and_sections() -> None:
    text = """ACTION: refuse
SKILL_NAME: skip-me
REFUSE_REASON: transient_failure
DESCRIPTION: none
TAGS: x
WHEN_TO_USE:
never
PROCEDURE:
1. no
"""
    parsed = SkillGenerator.__new__(SkillGenerator)._parse_skill_response(text)
    assert parsed["action"] == "refuse"
    assert parsed["refuse_reason"] == "transient_failure"
    assert "When to Use" in parsed["content"]


def test_save_skill_default_does_not_assign(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    mgr.save_skill(name="lonely", description="d", content="c")
    assert "lonely" not in (mgr.skill_assignments.get("main") or [])


@pytest.mark.asyncio
async def test_maybe_propose_does_not_write_skill_file(tmp_path: Path, monkeypatch) -> None:
    mgr = _mgr(tmp_path)
    agent = MagicMock()
    agent.skills = mgr
    agent.model = "coder"
    agent.client = MagicMock()
    agent.agent_slot = "main"
    agent.run_id = "run-1"
    agent.emit = MagicMock()

    async def _fake_should(_messages, _result):
        return True

    mgr.should_create_skill = _fake_should  # type: ignore[method-assign]

    fake = {
        "action": "create",
        "name": "session-learned-flow",
        "description": "Reusable FastAPI flow",
        "tags": ["fastapi"],
        "content": "## Procedure\n1. do it\n",
        "examples": [],
        "refuse_reason": "",
    }
    gen = MagicMock()
    gen.create_skill_from_session = AsyncMock(return_value=fake)
    monkeypatch.setattr(
        "core.skills.generator.SkillGenerator",
        MagicMock(return_value=gen),
    )

    rec = await maybe_propose_skill(
        agent,
        "conv-1",
        [
            {"role": "user", "content": "Собери FastAPI каталог с Dishka"},
            {"role": "assistant", "content": "ok"},
        ],
        "Готово.",
    )

    assert rec is not None
    assert rec["status"] == "pending"
    assert not (mgr.skills_dir / "session-learned-flow.md").exists()


@pytest.mark.asyncio
async def test_maybe_propose_from_subagent_stages_pending(tmp_path: Path, monkeypatch) -> None:
    mgr = _mgr(tmp_path)

    async def _fake_should(_messages, _result):
        return True

    mgr.should_create_skill = _fake_should  # type: ignore[method-assign]
    fake = {
        "action": "create",
        "name": "subagent-fastapi-flow",
        "description": "Reusable FastAPI flow from coder",
        "tags": ["fastapi"],
        "content": "## Procedure\n1. Context7\n2. write_file\n",
        "examples": [],
        "refuse_reason": "",
        "quality_score": 40,
    }
    gen = MagicMock()
    gen.create_skill_from_session = AsyncMock(return_value=fake)
    monkeypatch.setattr(
        "core.skills.generator.SkillGenerator",
        MagicMock(return_value=gen),
    )
    rec = await maybe_propose_skill_from_subagent(
        skills=mgr,
        client=MagicMock(),
        model="qwen3.6-35b",
        messages=[
            {"role": "user", "content": "Собери FastAPI каталог с Dishka"},
            {"role": "assistant", "content": "ok"},
        ],
        final_response="Готово.",
        conversation_id="subagent:p-proc-102d1-python-coder-x",
        profile="default",
        agent_slot="python-coder",
    )
    assert rec is not None
    assert rec["status"] == "pending"
    assert rec.get("agent_slot") == "python-coder"
    assert not (mgr.skills_dir / "subagent-fastapi-flow.md").exists()
    assert mgr.skill_assignments.get("main") in (None, [])
