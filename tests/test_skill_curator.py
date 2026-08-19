"""Deterministic curator: archive unused agent skills, skip bundled/pinned."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from core.di.runtime_config import HolixRuntimeConfig
from core.skills.curator import SkillCurator
from core.skills.manager import SkillsManager


def _mgr(tmp_path: Path) -> SkillsManager:
    return SkillsManager(
        HolixRuntimeConfig.from_settings().with_overrides(
            skills_dir=str(tmp_path / "skills"),
            vector_db_path=str(tmp_path / "vector"),
        )
    )


def _age(skill_path: Path, *, days: int, origin: str = "agent", pinned: bool = False) -> None:
    created = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    text = skill_path.read_text(encoding="utf-8")
    # Frontmatter already has created_at / origin from save_skill.
    text = text.replace("origin: agent", f"origin: {origin}")
    text = text.replace("origin: user", f"origin: {origin}")
    if "created_at:" in text:
        import re

        text = re.sub(r"created_at: .+", f"created_at: '{created}'", text, count=1)
    if pinned and "pinned:" not in text:
        text = text.replace("---\n", "---\npinned: true\n", 1)
    skill_path.write_text(text, encoding="utf-8")


def test_archives_old_unused_agent_skill(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    path = mgr.save_skill(
        name="old-agent-flow",
        description="unused",
        content="body",
        origin="agent",
    )
    _age(path, days=100, origin="agent")
    mgr.load_all_skills(defer_index=True)
    curator = SkillCurator(mgr, stale_after_days=30, archive_after_days=90)
    preview = curator.run(dry_run=True)
    assert "old-agent-flow" in preview["archived"]
    assert path.is_file()
    applied = curator.run(dry_run=False)
    assert "old-agent-flow" in applied["archived"]
    assert not path.is_file()
    assert any("old-agent-flow" in p.name for p in (mgr.skills_dir / "_archive").rglob("*.md"))
    mgr.load_all_skills(defer_index=True)
    assert "old-agent-flow" not in mgr.all_skills


def test_skips_bundled_and_pinned_and_user(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    user = mgr.save_skill(name="hand-written", description="mine", content="x", origin="user")
    pinned = mgr.save_skill(name="keep-me", description="pin", content="x", origin="agent")
    bundled = mgr.save_skill(
        name="holix-cron",
        description="bundled clone",
        content="x",
        origin="agent",
    )
    _age(user, days=120, origin="user")
    _age(pinned, days=120, origin="agent", pinned=True)
    _age(bundled, days=120, origin="agent")
    mgr.load_all_skills(defer_index=True)
    report = SkillCurator(mgr).run(dry_run=False)
    assert user.is_file()
    assert pinned.is_file()
    assert bundled.is_file()
    assert "hand-written" not in report["archived"]
    assert "keep-me" not in report["archived"]
    assert "holix-cron" not in report["archived"]


def test_restore_brings_skill_back(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    path = mgr.save_skill(name="restore-me", description="d", content="body", origin="agent")
    _age(path, days=120, origin="agent")
    mgr.load_all_skills(defer_index=True)
    curator = SkillCurator(mgr)
    curator.run(dry_run=False)
    restored = curator.restore("restore-me")
    assert restored.is_file()
    mgr.load_all_skills(defer_index=True)
    assert "restore-me" in mgr.all_skills
