"""Tests for hardened runtime memory cache."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.core import ProfileManager
from core.crypto.bootstrap import enable_profile_encryption
from core.crypto.memory_vault import purge_profile_memory_cache
from core.crypto.runtime_cache import (
    cache_dir_is_private,
    profile_runtime_cache_dir,
    recover_stale_runtime_caches,
    runtime_cache_root,
)
from core.crypto.unlock_context import set_profile_session_unlock
from core.paths import prepare_sqlite_db_file


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_runtime_cache_lives_under_holix_home(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("alice", inherit_global=False)
    pdir = manager.get_profile_dir("alice")
    memory_db = pdir / "data" / "memory" / "memory.db"
    memory_db.parent.mkdir(parents=True, exist_ok=True)
    import sqlite3

    conn = sqlite3.connect(str(memory_db))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    enable_profile_encryption(manager, "alice", "unlock-key-alice-99")
    from core.crypto.profile_crypto import unlock_profile_dek

    set_profile_session_unlock("alice", unlock_profile_dek("alice", "unlock-key-alice-99"))
    prepare_sqlite_db_file(str(memory_db))

    cache_dir = profile_runtime_cache_dir("alice")
    assert cache_dir.is_dir()
    assert cache_dir.is_relative_to(runtime_cache_root())
    assert not (pdir / "data" / ".holix" / "memory-cache").exists()
    assert cache_dir_is_private(cache_dir)


def test_recover_stale_runtime_caches_removes_plaintext(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("bob", inherit_global=False)
    legacy = manager.get_profile_dir("bob") / "data" / ".holix" / "memory-cache"
    legacy.mkdir(parents=True)
    (legacy / "memory.db").write_bytes(b"plaintext")

    runtime = profile_runtime_cache_dir("bob")
    runtime.mkdir(parents=True)
    (runtime / "memory.db").write_bytes(b"plaintext")

    stats = recover_stale_runtime_caches()
    assert stats["legacy_removed"] >= 1
    assert stats["runtime_removed"] >= 1
    assert not legacy.exists()
    assert not runtime.exists()


def test_purge_profile_cache(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    cache = profile_runtime_cache_dir("carol")
    cache.mkdir(parents=True)
    (cache / "memory.db").write_bytes(b"x")
    assert purge_profile_memory_cache("carol") >= 1
    assert not cache.exists()