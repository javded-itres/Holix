"""Bundled default skills (helix-cron)."""

from __future__ import annotations

from pathlib import Path

from core.hub.normalize import parse_skill_file
from core.skills.bundled import (
    bundled_skills_root,
    ensure_bundled_assigned_to_main,
    seed_bundled_skills,
)


def test_bundled_helix_cron_skill_exists():
    skill_md = bundled_skills_root() / "helix-cron" / "SKILL.md"
    assert skill_md.is_file()
    parsed = parse_skill_file(skill_md)
    assert parsed is not None
    assert parsed["name"] == "helix-cron"
    assert "crontab" in parsed["content"].lower()
    assert "/cron add" in parsed["content"]


def test_seed_bundled_skills(tmp_path: Path):
    dest = tmp_path / "skills"
    first = seed_bundled_skills(dest)
    assert "helix-cron" in first
    assert (dest / "helix-cron.md").is_file()

    second = seed_bundled_skills(dest)
    assert second == []

    third = seed_bundled_skills(dest, overwrite=True)
    assert "helix-cron" in third


def test_ensure_bundled_assigned_to_main():
    assigns, added = ensure_bundled_assigned_to_main({"main": ["docker-manager"]})
    assert "helix-cron" in added
    assert "helix-cron" in assigns["main"]
    assert "docker-manager" in assigns["main"]