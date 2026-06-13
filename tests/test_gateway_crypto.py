"""Gateway multi-profile crypto unlock tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from cli.core import ProfileManager
from core.crypto.encrypted_fs import is_encrypted_file
from core.crypto.gateway_crypto import (
    GatewayProfileLockedError,
    ensure_gateway_profile_unlock,
    release_gateway_profile_unlock,
    require_gateway_profile_unlock,
)
from core.crypto.unlock_context import clear_profile_session_unlock, get_profile_session_dek
from core.paths import prepare_sqlite_db_file


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _seed_memory(profile_dir: Path) -> None:
    memory_db = profile_dir / "data" / "memory" / "memory.db"
    memory_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(memory_db))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('secret')")
    conn.commit()
    conn.close()


def test_ensure_unlock_with_env_key(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("alice", inherit_global=False)
    from core.crypto.bootstrap import enable_profile_encryption

    _seed_memory(manager.get_profile_dir("alice"))
    enable_profile_encryption(manager, "alice", "unlock-key-alice-99")
    clear_profile_session_unlock("alice")

    monkeypatch.setenv("HOLIX_UNLOCK_KEY", "unlock-key-alice-99")
    assert ensure_gateway_profile_unlock("alice") is True
    assert get_profile_session_dek("alice") is not None


def test_require_unlock_raises_without_key(holix_home, monkeypatch) -> None:
    monkeypatch.delenv("HOLIX_UNLOCK_KEY", raising=False)
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("bob", inherit_global=False)
    from core.crypto.bootstrap import enable_profile_encryption

    enable_profile_encryption(manager, "bob", "unlock-key-bob-1234", encrypt_existing=False)
    clear_profile_session_unlock("bob")

    with pytest.raises(GatewayProfileLockedError):
        require_gateway_profile_unlock("bob")


def test_release_seals_memory(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("carol", inherit_global=False)
    pdir = manager.get_profile_dir("carol")
    from core.crypto.bootstrap import enable_profile_encryption

    _seed_memory(pdir)
    enable_profile_encryption(manager, "carol", "unlock-key-carol-88")
    memory_db = pdir / "data" / "memory" / "memory.db"

    monkeypatch.setenv("HOLIX_UNLOCK_KEY", "unlock-key-carol-88")
    ensure_gateway_profile_unlock("carol")
    prepare_sqlite_db_file(str(memory_db))

    release_gateway_profile_unlock("carol")
    assert get_profile_session_dek("carol") is None
    assert is_encrypted_file(memory_db)