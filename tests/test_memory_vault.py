"""Tests for encrypted profile memory stores."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from cli.core import ProfileManager
from core.crypto.bootstrap import enable_profile_encryption, seal_profiles_secrets
from core.crypto.encrypted_fs import ENCRYPTION_MAGIC, is_encrypted_file
from core.crypto.memory_vault import (
    VECTOR_SEALED_FILENAME,
    encrypt_profile_memory,
    resolve_memory_sqlite_path,
    resolve_memory_vector_dir,
    seal_profile_memory,
)
from core.crypto.profile_crypto import ProfileCryptoLockedError
from core.crypto.unlock_context import (
    clear_profile_session_unlock,
    clear_profile_unlock,
    set_profile_session_unlock,
)
from core.paths import prepare_sqlite_db_file


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_sqlite_dialog(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS conversations "
        "(id INTEGER PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT)"
    )
    conn.execute(
        "INSERT INTO conversations (conversation_id, role, content) VALUES (?, ?, ?)",
        ("c1", "user", text),
    )
    conn.commit()
    conn.close()


def test_memory_db_sealed_at_rest(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("alice", inherit_global=False)
    pdir = manager.get_profile_dir("alice")
    memory_db = pdir / "data" / "memory" / "memory.db"
    secret = "super-secret-dialog-phrase-xyz"
    _write_sqlite_dialog(memory_db, secret)

    enable_profile_encryption(manager, "alice", "unlock-key-alice-99")

    assert is_encrypted_file(memory_db)
    assert secret.encode() not in memory_db.read_bytes()
    assert memory_db.read_bytes().startswith(ENCRYPTION_MAGIC)


def test_memory_round_trip_after_unlock(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("bob", inherit_global=False)
    pdir = manager.get_profile_dir("bob")
    memory_db = pdir / "data" / "memory" / "memory.db"
    secret = "private-memory-content-abc"
    _write_sqlite_dialog(memory_db, secret)

    enable_profile_encryption(manager, "bob", "unlock-key-bob-1234")
    clear_profile_session_unlock("bob")

    from core.crypto.profile_crypto import unlock_profile_dek

    set_profile_session_unlock("bob", unlock_profile_dek("bob", "unlock-key-bob-1234"))
    working = prepare_sqlite_db_file(str(memory_db))
    conn = sqlite3.connect(str(working))
    row = conn.execute("SELECT content FROM conversations LIMIT 1").fetchone()
    conn.close()
    assert row is not None
    assert row[0] == secret


def test_locked_memory_raises(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("carol", inherit_global=False)
    pdir = manager.get_profile_dir("carol")
    memory_db = pdir / "data" / "memory" / "memory.db"
    _write_sqlite_dialog(memory_db, "locked-data")
    enable_profile_encryption(manager, "carol", "unlock-key-carol-88")
    clear_profile_session_unlock("carol")

    with pytest.raises(ProfileCryptoLockedError):
        resolve_memory_sqlite_path(memory_db)


def test_seal_existing_memory_on_encrypted_profile(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("dave", inherit_global=False)
    pdir = manager.get_profile_dir("dave")
    memory_db = pdir / "data" / "memory" / "memory.db"
    _write_sqlite_dialog(memory_db, "late-added-memory")

    enable_profile_encryption(manager, "dave", "unlock-key-dave-11", encrypt_existing=False)
    assert not is_encrypted_file(memory_db)

    summary = seal_profiles_secrets(manager, "unlock-key-dave-11", profiles=["dave"])
    assert len(summary.migrated) == 1
    assert summary.migrated[0].memory_sealed >= 1
    assert is_encrypted_file(memory_db)


def test_lock_seals_materialized_memory(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("erin", inherit_global=False)
    pdir = manager.get_profile_dir("erin")
    memory_db = pdir / "data" / "memory" / "memory.db"
    _write_sqlite_dialog(memory_db, "seal-on-lock-test")

    from core.crypto.profile_crypto import unlock_profile_dek

    enable_profile_encryption(manager, "erin", "unlock-key-erin-55")
    dek = unlock_profile_dek("erin", "unlock-key-erin-55")
    set_profile_session_unlock("erin", dek)
    prepare_sqlite_db_file(str(memory_db))

    clear_profile_unlock("erin")
    assert is_encrypted_file(memory_db)


def test_vector_db_sealed(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("frank", inherit_global=False)
    pdir = manager.get_profile_dir("frank")
    vector_dir = pdir / "data" / "memory" / "vector_db"
    vector_dir.mkdir(parents=True, exist_ok=True)
    secret_file = vector_dir / "chroma.sqlite3"
    secret_file.write_text("vector-secret-data", encoding="utf-8")

    from core.crypto.profile_crypto import unlock_profile_dek

    enable_profile_encryption(manager, "frank", "unlock-key-frank-77", encrypt_existing=False)
    dek = unlock_profile_dek("frank", "unlock-key-frank-77")
    count = encrypt_profile_memory("frank", dek)
    assert count >= 1

    sealed = pdir / "data" / "memory" / VECTOR_SEALED_FILENAME
    assert sealed.is_file()
    assert is_encrypted_file(sealed)
    assert not vector_dir.exists()
    assert b"vector-secret-data" not in sealed.read_bytes()


def test_vector_round_trip(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("grace", inherit_global=False)
    pdir = manager.get_profile_dir("grace")
    vector_dir = pdir / "data" / "memory" / "vector_db"
    vector_dir.mkdir(parents=True, exist_ok=True)
    marker = vector_dir / "marker.txt"
    marker.write_text("chroma-marker", encoding="utf-8")

    from core.crypto.profile_crypto import unlock_profile_dek

    enable_profile_encryption(manager, "grace", "unlock-key-grace-42", encrypt_existing=False)
    dek = unlock_profile_dek("grace", "unlock-key-grace-42")
    seal_profile_memory("grace", dek)

    clear_profile_session_unlock("grace")
    set_profile_session_unlock("grace", dek)
    working = resolve_memory_vector_dir(vector_dir)
    assert (working / "marker.txt").read_text(encoding="utf-8") == "chroma-marker"