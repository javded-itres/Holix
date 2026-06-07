"""Tests for /skills slash command and main-agent skill visibility."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli.core import ProfileConfig, ProfileManager
from core.di import resolve_runtime_config
from core.skills.assignments import is_skill_allowed_for_agent
from core.skills.manager import SkillsManager


def test_main_agent_not_limited_by_skill_assignments(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cli.core.PROFILES_DIR", tmp_path / "profiles")
    manager = ProfileManager()
    profile = "default"
    profile_dir = manager.get_profile_dir(profile)
    skills_dir = profile_dir / "data" / "skills"
    skills_dir.mkdir(parents=True)

    for name in ("allowed-skill", "blocked-in-assignments"):
        (skills_dir / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: {name}\ntags: []\n---\nbody\n",
            encoding="utf-8",
        )

    (profile_dir / "config.yaml").write_text(
        "profile_name: default\nmodel: test\n"
        "skill_assignments:\n  main:\n    - allowed-skill\n",
        encoding="utf-8",
    )

    cfg = manager.load_profile(profile)
    runtime = resolve_runtime_config(cfg)
    mgr = SkillsManager(runtime)
    mgr.load_all_skills()

    assert "blocked-in-assignments" in mgr.all_skills
    assert is_skill_allowed_for_agent(
        mgr.all_skills["blocked-in-assignments"], "main", cfg.skill_assignments
    )
    assert not is_skill_allowed_for_agent(
        mgr.all_skills["blocked-in-assignments"], "coder", {"coder": ["other"]}
    )


@pytest.mark.asyncio
async def test_run_skills_command_lists_profile_skills(tmp_path, monkeypatch) -> None:
    from cli.shared.commands.skills_commands import format_skills_message

    monkeypatch.setattr("cli.core.PROFILES_DIR", tmp_path / "profiles")
    manager = ProfileManager()
    profile = "default"
    profile_dir = manager.get_profile_dir(profile)
    skills_dir = profile_dir / "data" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "demo-skill.md").write_text(
        "---\nname: demo-skill\ndescription: Demo\n---\n",
        encoding="utf-8",
    )
    (profile_dir / "config.yaml").write_text("profile_name: default\nmodel: test\n", encoding="utf-8")

    host_cfg = manager.load_profile(profile)

    class Host:
        def __init__(self) -> None:
            self.profile = profile
            self.config = host_cfg
            self.agent = None
            self.agent_slot = "main"
            self.last = ""

        def transcript_write(self, text: str) -> None:
            self.last = text

    host = Host()
    msg = format_skills_message(host, html=False)
    assert "demo-skill" in msg
    assert "loaded 1" in msg


def test_save_skill_auto_assigns_to_agent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cli.core.PROFILES_DIR", tmp_path / "profiles")
    manager = ProfileManager()
    profile = "default"
    profile_dir = manager.get_profile_dir(profile)
    skills_dir = profile_dir / "data" / "skills"
    skills_dir.mkdir(parents=True)
    (profile_dir / "config.yaml").write_text(
        "profile_name: default\nmodel: test\nskill_assignments:\n  main:\n    - old-skill\n",
        encoding="utf-8",
    )

    cfg = manager.load_profile(profile)
    from core.di import resolve_runtime_config

    runtime = resolve_runtime_config(cfg)
    mgr = SkillsManager(runtime)
    mgr.save_skill(
        name="agent-made",
        description="Created by agent",
        content="steps",
        agent_slot="main",
    )

    assert "agent-made" in mgr.skill_assignments.get("main", [])
    reloaded = manager.load_profile(profile)
    assert "agent-made" in (reloaded.skill_assignments or {}).get("main", [])
    assert "old-skill" in (reloaded.skill_assignments or {}).get("main", [])