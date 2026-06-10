"""Ensure Helix runtime data never lands in process CWD."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.core import ProfileConfig, ProfileManager, resolve_profile_storage_paths
from core.di.runtime_config import HelixRuntimeConfig
from core.memory.ltm import LongTermMemoryStore
from core.security.confirmation import ActionGuard, PermissionManager


def test_from_profile_resolves_all_memory_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cli.core.PROFILES_DIR", tmp_path / "profiles")
    profile_dir = ProfileManager().get_profile_dir("work")
    profile_dir.mkdir(parents=True)

    cfg = ProfileConfig(profile_name="work")
    resolved = resolve_profile_storage_paths("work", cfg, profile_dir=profile_dir)
    runtime = HelixRuntimeConfig.from_profile(resolved)

    assert runtime.ltm_db_path == str((profile_dir / "data" / "memory" / "ltm.db").resolve())
    assert runtime.langgraph_checkpoint_db_path == str(
        (profile_dir / "data" / "memory" / "checkpoints.db").resolve()
    )
    assert not Path(runtime.ltm_db_path).is_relative_to(Path.cwd())


def test_ltm_store_uses_profile_path_not_cwd(tmp_path, monkeypatch) -> None:
    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.chdir(project)
    monkeypatch.setattr("cli.core.PROFILES_DIR", tmp_path / "profiles")

    profile_dir = ProfileManager().get_profile_dir("default")
    profile_dir.mkdir(parents=True)
    cfg = resolve_profile_storage_paths(
        "default",
        ProfileConfig(profile_name="default"),
        profile_dir=profile_dir,
    )
    runtime = HelixRuntimeConfig.from_profile(cfg)

    LongTermMemoryStore(runtime)

    assert (profile_dir / "data" / "memory" / "ltm.db").parent.exists()
    assert not (tmp_path / "project" / "data").exists()


def test_permission_manager_uses_profile_data_dir(tmp_path, monkeypatch) -> None:
    profile_data = tmp_path / "profiles" / "default" / "data"
    profile_data.mkdir(parents=True)
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    monkeypatch.chdir(repo)

    pm = PermissionManager(data_dir=profile_data)
    pm.save()

    assert (profile_data / "security" / "permissions.json").exists()
    assert not (tmp_path / "repo" / "data").exists()


@pytest.mark.asyncio
async def test_action_guard_audit_log_in_profile(tmp_path, monkeypatch) -> None:
    profile_data = tmp_path / "profiles" / "default" / "data"
    profile_data.mkdir(parents=True)
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    monkeypatch.chdir(repo)

    pm = PermissionManager(data_dir=profile_data)
    guard = ActionGuard(
        permission_manager=pm,
        interactive=False,
        data_dir=profile_data,
    )

    class _Tool:
        name = "noop"
        risk_level = "high"

    async def _run() -> str:
        return "ok"

    await guard.check_and_execute("noop", _Tool(), {}, _run)

    audit = profile_data / "security" / "confirmation_audit.jsonl"
    assert audit.exists()
    assert not (tmp_path / "repo" / "data").exists()


def test_doctor_migrates_stray_project_data(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cli.core.PROFILES_DIR", tmp_path / "profiles")
    repo = tmp_path / "repo"
    repo.mkdir()
    stray = repo / "data" / "memory"
    stray.mkdir(parents=True)
    (stray / "ltm.db").write_bytes(b"sqlite")

    monkeypatch.chdir(repo)
    from cli.doctor.checks import _check_stray_project_data
    from cli.doctor.fixes import apply_deterministic_fixes

    findings = _check_stray_project_data("default", ProfileManager())
    assert findings and findings[0].fix_id == "migrate_stray_data"

    applied = apply_deterministic_fixes("default", findings)
    assert applied
    assert not (repo / "data").exists()
    assert (tmp_path / "profiles" / "default" / "data" / "memory" / "ltm.db").exists()