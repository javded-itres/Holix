"""Bundled default skills (holix-cron, holix-subagents)."""

from __future__ import annotations

from pathlib import Path

from core.hub.normalize import parse_skill_file
from core.skills.bundled import (
    bundled_skills_root,
    ensure_bundled_assigned_to_main,
    seed_bundled_skills,
)


def test_bundled_holix_cron_skill_exists():
    skill_md = bundled_skills_root() / "holix-cron" / "SKILL.md"
    assert skill_md.is_file()
    parsed = parse_skill_file(skill_md)
    assert parsed is not None
    assert parsed["name"] == "holix-cron"
    assert "crontab" in parsed["content"].lower()
    assert "/cron add" in parsed["content"]


def test_bundled_holix_subagents_skill_exists():
    skill_md = bundled_skills_root() / "holix-subagents" / "SKILL.md"
    assert skill_md.is_file()
    parsed = parse_skill_file(skill_md)
    assert parsed is not None
    assert parsed["name"] == "holix-subagents"
    assert "delegate_to_subagent" in parsed["content"]
    assert "/subagent-reply" in parsed["content"]
    assert "holix launch" in parsed["content"]


def test_seed_bundled_skills(tmp_path: Path):
    dest = tmp_path / "skills"
    first = seed_bundled_skills(dest)
    assert "holix-cron" in first
    assert "holix-subagents" in first
    assert (dest / "holix-cron.md").is_file()
    assert (dest / "holix-subagents.md").is_file()

    second = seed_bundled_skills(dest)
    assert second == []

    third = seed_bundled_skills(dest, overwrite=True)
    assert "holix-cron" in third


def test_ensure_bundled_assigned_to_main():
    assigns, added = ensure_bundled_assigned_to_main({"main": ["docker-manager"]})
    assert "holix-cron" in added
    assert "holix-subagents" in added
    assert "holix-cron" in assigns["main"]
    assert "holix-subagents" in assigns["main"]
    assert "docker-manager" in assigns["main"]