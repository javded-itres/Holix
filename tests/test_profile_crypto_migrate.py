"""Tests for bulk profile encryption migration."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.core import ProfileManager
from core.crypto.bootstrap import (
    list_unencrypted_profiles,
    migrate_profiles_encryption,
)
from core.crypto.encrypted_fs import is_encrypted_file
from core.crypto.profile_crypto import create_profile_crypto, is_profile_encryption_enabled


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _seed_profile(manager: ProfileManager, name: str, *, plaintext_file: bool = False) -> None:
    manager.create_profile(name, inherit_global=False)
    if plaintext_file:
        workspace = manager.get_profile_dir(name) / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "notes.txt").write_text("secret notes", encoding="utf-8")


def test_list_unencrypted_profiles(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    _seed_profile(manager, "alice")
    _seed_profile(manager, "bob")
    create_profile_crypto("bob", "unlock-key-bob-12")

    assert list_unencrypted_profiles(manager) == ["alice"]


def test_migrate_all_profiles_encrypts_workspace(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    _seed_profile(manager, "alice", plaintext_file=True)
    _seed_profile(manager, "carol", plaintext_file=True)

    summary = migrate_profiles_encryption(
        manager,
        "shared-unlock-key-99",
        profiles=["alice", "carol"],
    )

    assert len(summary.migrated) == 2
    assert summary.skipped == []
    assert summary.failed == []

    for name in ("alice", "carol"):
        assert is_profile_encryption_enabled(name)
        config = manager.load_profile(name)
        assert config.encryption_enabled is True
        assert config.workspace_jail_enabled is True
        target = manager.get_profile_dir(name) / "workspace" / "notes.txt"
        assert is_encrypted_file(target)
        assert b"secret notes" not in target.read_bytes()


def test_migrate_skips_already_encrypted(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    _seed_profile(manager, "alice")
    create_profile_crypto("alice", "unlock-key-alice-1")

    summary = migrate_profiles_encryption(
        manager,
        "shared-unlock-key-99",
        profiles=["alice"],
    )

    assert summary.migrated == []
    assert summary.skipped == ["alice"]


def test_bootstrap_profile_unlock_from_env(holix_home, monkeypatch) -> None:
    from cli.core import bootstrap_profile_unlock_from_env
    from core.crypto.unlock_context import get_profile_session_dek

    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    _seed_profile(manager, "alice")
    migrate_profiles_encryption(manager, "env-unlock-key-42", profiles=["alice"])
    from core.crypto.unlock_context import clear_profile_session_unlock

    clear_profile_session_unlock("alice")
    monkeypatch.delenv("HOLIX_UNLOCK_KEY", raising=False)
    assert get_profile_session_dek("alice") is None

    monkeypatch.setenv("HOLIX_UNLOCK_KEY", "env-unlock-key-42")
    assert bootstrap_profile_unlock_from_env("alice") is True
    assert get_profile_session_dek("alice") is not None