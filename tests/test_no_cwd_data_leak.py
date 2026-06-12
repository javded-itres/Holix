"""Ensure Holix runtime data never lands in process CWD."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.core import ProfileConfig, ProfileManager, resolve_profile_storage_paths
from core.di.runtime_config import HolixRuntimeConfig
from core.memory.ltm import LongTermMemoryStore
from core.security.confirmation import ActionGuard, PermissionManager


def test_from_profile_resolves_all_memory_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cli.core.PROFILES_DIR", tmp_path / "profiles")
    profile_dir = ProfileManager().get_profile_dir("work")
    profile_dir.mkdir(parents=True)

    cfg = ProfileConfig(profile_name="work")
    resolved = resolve_profile_storage_paths("work", cfg, profile_dir=profile_dir)
    runtime = HolixRuntimeConfig.from_profile(resolved)

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
    runtime = HolixRuntimeConfig.from_profile(cfg)

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


def test_ltm_path_always_colocated_with_memory_db(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cli.core.PROFILES_DIR", tmp_path / "profiles")
    profile_dir = ProfileManager().get_profile_dir("default")
    profile_dir.mkdir(parents=True)

    cfg = ProfileConfig(
        profile_name="default",
        memory_db_path=str(profile_dir / "data" / "memory" / "memory.db"),
        ltm_db_path="/tmp/other/ltm.db",
    )
    resolved = resolve_profile_storage_paths("default", cfg, profile_dir=profile_dir)
    memory_dir = profile_dir / "data" / "memory"
    assert Path(resolved.ltm_db_path) == (memory_dir / "ltm.db").resolve()
    assert Path(resolved.langgraph_checkpoint_db_path) == (memory_dir / "checkpoints.db").resolve()


def test_prepare_sqlite_recovers_when_db_path_is_directory(tmp_path) -> None:
    from core.paths import prepare_sqlite_db_file

    db_path = tmp_path / "ltm.db"
    db_path.mkdir()
    opened = prepare_sqlite_db_file(db_path)
    assert opened == db_path.resolve()
    assert db_path.is_file()
    assert not db_path.is_dir()
    backups = list(tmp_path.glob("ltm.db.holix-bak*"))
    assert backups


def test_stale_absolute_ltm_path_reset_to_profile(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cli.core.PROFILES_DIR", tmp_path / "profiles")
    profile_dir = ProfileManager().get_profile_dir("default")
    profile_dir.mkdir(parents=True)

    cfg = ProfileConfig(
        profile_name="default",
        ltm_db_path="/root/.holix-stale/ltm.db",
        memory_db_path="/root/.holix-stale/memory.db",
    )
    resolved = resolve_profile_storage_paths("default", cfg, profile_dir=profile_dir)
    expected = (profile_dir / "data" / "memory" / "ltm.db").resolve()
    assert Path(resolved.ltm_db_path) == expected
    assert Path(resolved.memory_db_path) == (profile_dir / "data" / "memory" / "memory.db").resolve()


def test_api_keys_db_resolves_under_holix_home(tmp_path, monkeypatch) -> None:
    holix_home = tmp_path / "holix"
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    monkeypatch.chdir(repo)

    from core.paths import resolve_api_keys_db_path

    resolved = resolve_api_keys_db_path("security/api_keys.db")
    assert resolved == (holix_home / "security" / "api_keys.db").resolve()
    assert not resolved.is_relative_to(repo)


@pytest.mark.asyncio
async def test_api_key_manager_opens_resolved_db(tmp_path, monkeypatch) -> None:
    holix_home = tmp_path / "holix"
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    monkeypatch.chdir(repo)

    from config import settings
    from core.security.auth import APIKeyManager

    updated = settings.model_copy(update={"api_key_pepper": "test-pepper"})
    monkeypatch.setattr("config.settings", updated)
    monkeypatch.setattr("core.security.auth.settings", updated)

    mgr = APIKeyManager()
    await mgr.initialize_db()
    assert mgr.db_path == (holix_home / "security" / "api_keys.db").resolve()
    assert mgr.db_path.exists()


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