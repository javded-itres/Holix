"""Bundled default skills (holix-cron, holix-subagents, holix-sdd-*)."""

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


def test_bundled_holix_sdd_skills_exist():
    for name in ("holix-sdd-propose", "holix-sdd-apply", "holix-sdd-archive"):
        skill_md = bundled_skills_root() / name / "SKILL.md"
        assert skill_md.is_file(), name
        parsed = parse_skill_file(skill_md)
        assert parsed is not None
        assert parsed["name"] == name
    apply = parse_skill_file(bundled_skills_root() / "holix-sdd-apply" / "SKILL.md")
    assert "sdd_set_apply_mode" in apply["content"]
    assert "subagents" in apply["content"]
    propose = parse_skill_file(bundled_skills_root() / "holix-sdd-propose" / "SKILL.md")
    assert "assignee" in propose["content"]


def test_bundled_holix_studio_frontend_backend_skill_exists():
    skill_md = bundled_skills_root() / "holix-studio-frontend-backend" / "SKILL.md"
    assert skill_md.is_file()
    parsed = parse_skill_file(skill_md)
    assert parsed is not None
    assert parsed["name"] == "holix-studio-frontend-backend"
    body = parsed["content"].lower()
    assert "0.0.0.0" in body or "0.0.0.0" in parsed["content"]
    assert "open_preview_url" in parsed["content"]
    assert "docker-compose" in body or "docker compose" in body
    assert "nginx" in body
    assert "preview" in body
    # Platform / required flags
    assert parsed.get("required") is True or parsed.get("platform") is True or "required" in (
        parsed.get("tags") or []
    )


def test_seed_bundled_skills(tmp_path: Path):
    from core.skills.bundled import required_bundled_skill_names

    dest = tmp_path / "skills"
    first = seed_bundled_skills(dest)
    assert "holix-cron" in first
    assert "holix-subagents" in first
    assert "holix-sdd-propose" in first
    assert "holix-studio-frontend-backend" in first
    assert (dest / "holix-cron.md").is_file()
    assert (dest / "holix-subagents.md").is_file()
    assert (dest / "holix-sdd-apply.md").is_file()
    assert (dest / "holix-studio-frontend-backend.md").is_file()

    # Non-required skills are not re-seeded; required platform skill is refreshed
    fe = dest / "holix-studio-frontend-backend.md"
    fe.write_text("stale", encoding="utf-8")
    second = seed_bundled_skills(dest)
    assert "holix-cron" not in second
    assert "holix-studio-frontend-backend" in second
    assert "stale" not in fe.read_text(encoding="utf-8")
    assert "holix-studio-frontend-backend" in required_bundled_skill_names()

    third = seed_bundled_skills(dest, overwrite=True)
    assert "holix-cron" in third


def test_ensure_bundled_assigned_to_main():
    assigns, added = ensure_bundled_assigned_to_main({"main": ["docker-manager"]})
    assert "holix-cron" in added
    assert "holix-subagents" in added
    assert "holix-sdd-propose" in added
    assert "holix-studio-frontend-backend" in added
    assert "holix-cron" in assigns["main"]
    assert "holix-subagents" in assigns["main"]
    assert "holix-studio-frontend-backend" in assigns["main"]
    assert "docker-manager" in assigns["main"]
