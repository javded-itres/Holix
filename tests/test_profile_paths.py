"""Profile storage path resolution."""

from __future__ import annotations

from pathlib import Path

from cli.core import ProfileConfig, ProfileManager, resolve_profile_storage_paths


def test_resolve_profile_storage_paths_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cli.core.PROFILES_DIR", tmp_path / "profiles")
    profile = "work"
    profile_dir = ProfileManager().get_profile_dir(profile)
    profile_dir.mkdir(parents=True)

    cfg = ProfileConfig(profile_name=profile)
    resolved = resolve_profile_storage_paths(profile, cfg, profile_dir=profile_dir)

    assert resolved.skills_dir == str((profile_dir / "data" / "skills").resolve())
    assert resolved.memory_db_path == str(
        (profile_dir / "data" / "memory" / "memory.db").resolve()
    )


def test_resolve_profile_storage_paths_relative_to_profile(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cli.core.PROFILES_DIR", tmp_path / "profiles")
    profile = "default"
    profile_dir = ProfileManager().get_profile_dir(profile)
    profile_dir.mkdir(parents=True)

    cfg = ProfileConfig(profile_name=profile, skills_dir="data/skills")
    resolved = resolve_profile_storage_paths(profile, cfg, profile_dir=profile_dir)

    assert Path(resolved.skills_dir) == (profile_dir / "data" / "skills").resolve()


def test_load_profile_uses_profile_skills_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cli.core.PROFILES_DIR", tmp_path / "profiles")
    manager = ProfileManager()
    profile = "tg"
    profile_dir = manager.get_profile_dir(profile)
    (profile_dir / "data" / "skills").mkdir(parents=True)
    skill = profile_dir / "data" / "skills" / "my-skill.md"
    skill.write_text(
        "---\nname: my-skill\ndescription: test\ntags: []\n---\nbody\n",
        encoding="utf-8",
    )
    (profile_dir / "config.yaml").write_text(
        "profile_name: tg\nmodel: test\n",
        encoding="utf-8",
    )

    cfg = manager.load_profile(profile)
    from core.di import resolve_runtime_config
    from core.skills.manager import SkillsManager

    runtime = resolve_runtime_config(cfg)
    mgr = SkillsManager(runtime)
    mgr.load_all_skills()

    assert runtime.skills_dir == str((profile_dir / "data" / "skills").resolve())
    assert "my-skill" in mgr.all_skills