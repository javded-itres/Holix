"""Tests for encrypted profile secret files (.env, SOUL.md, …)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from cli.core import ProfileManager
from core.crypto.bootstrap import enable_profile_encryption, seal_profiles_secrets
from core.crypto.encrypted_fs import is_encrypted_file
from core.crypto.profile_files import read_profile_file_text
from core.crypto.unlock_context import (
    bootstrap_profile_unlock_from_env,
    clear_profile_session_unlock,
)


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_enable_encrypts_profile_secrets(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("alice", inherit_global=False)
    pdir = manager.get_profile_dir("alice")
    (pdir / ".env").write_text("API_KEY=secret123\n", encoding="utf-8")
    (pdir / "SOUL.md").write_text("# Soul\nPrivate soul text\n", encoding="utf-8")

    result = enable_profile_encryption(manager, "alice", "unlock-key-alice-99")
    assert result.secrets_encrypted >= 2
    assert is_encrypted_file(pdir / ".env")
    assert is_encrypted_file(pdir / "SOUL.md")
    assert b"secret123" not in (pdir / ".env").read_bytes()


def test_seal_existing_encrypted_profile(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("bob", inherit_global=False)
    pdir = manager.get_profile_dir("bob")
    enable_profile_encryption(manager, "bob", "unlock-key-bob-1234", encrypt_existing=False)
    (pdir / "USER.md").write_text("# User\nAlice\n", encoding="utf-8")

    summary = seal_profiles_secrets(manager, "unlock-key-bob-1234", profiles=["bob"])
    assert len(summary.migrated) == 1
    assert summary.migrated[0].secrets_encrypted >= 1
    assert is_encrypted_file(pdir / "USER.md")


def test_bootstrap_profile_env_reads_encrypted_dotenv(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("dana", inherit_global=False)
    pdir = manager.get_profile_dir("dana")
    (pdir / ".env").write_text("MY_TOKEN=secret-dana\n", encoding="utf-8")
    enable_profile_encryption(manager, "dana", "unlock-key-dana-42")

    monkeypatch.setenv("HOLIX_UNLOCK_KEY", "unlock-key-dana-42")
    from core.env_loader import bootstrap_profile_env, read_profile_env_map

    bootstrap_profile_env("dana", force=True)
    assert os.environ.get("MY_TOKEN") == "secret-dana"
    assert read_profile_env_map("dana") == {"MY_TOKEN": "secret-dana"}


def test_read_secrets_after_env_unlock(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("carol", inherit_global=False)
    pdir = manager.get_profile_dir("carol")
    (pdir / ".env").write_text("TOKEN=abc\n", encoding="utf-8")
    enable_profile_encryption(manager, "carol", "unlock-key-carol-88")
    clear_profile_session_unlock("carol")

    monkeypatch.setenv("HOLIX_UNLOCK_KEY", "unlock-key-carol-88")
    assert bootstrap_profile_unlock_from_env("carol") is True
    text = read_profile_file_text(pdir / ".env", profile="carol")
    assert "TOKEN=abc" in text