"""Auto-reset of LangGraph checkpoints.db when over size limit."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.persistence import (
    checkpoint_bundle_size_bytes,
    clear_checkpoint_prune_cooldown,
    maybe_reset_checkpoint_db,
)


@pytest.fixture(autouse=True)
def _clear_cooldown():
    clear_checkpoint_prune_cooldown()
    yield
    clear_checkpoint_prune_cooldown()


def _write_fake_checkpoint(root: Path, *, main_bytes: int, wal_bytes: int = 0) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    db = root / "checkpoints.db"
    db.write_bytes(b"x" * main_bytes)
    if wal_bytes:
        Path(f"{db}-wal").write_bytes(b"y" * wal_bytes)
    return db


def test_bundle_size_includes_wal(tmp_path: Path) -> None:
    db = _write_fake_checkpoint(tmp_path, main_bytes=1000, wal_bytes=500)
    assert checkpoint_bundle_size_bytes(db) == 1500


def test_under_limit_not_pruned(tmp_path: Path) -> None:
    db = _write_fake_checkpoint(tmp_path, main_bytes=100)
    result = maybe_reset_checkpoint_db(db, max_bytes=1000, enabled=True, cooldown_s=0)
    assert result["pruned"] is False
    assert result["reason"] == "under_limit"
    assert db.is_file()


def test_over_limit_deletes_db_and_sidecars(tmp_path: Path) -> None:
    db = _write_fake_checkpoint(tmp_path, main_bytes=800, wal_bytes=300)
    wal = Path(f"{db}-wal")
    assert wal.is_file()

    result = maybe_reset_checkpoint_db(db, max_bytes=500, enabled=True, cooldown_s=0)
    assert result["pruned"] is True
    assert result["reason"] == "reset"
    assert result["size_before"] == 1100
    assert not db.exists()
    assert not wal.exists()


def test_disabled_skips(tmp_path: Path) -> None:
    db = _write_fake_checkpoint(tmp_path, main_bytes=10_000)
    result = maybe_reset_checkpoint_db(db, max_bytes=10, enabled=False, cooldown_s=0)
    assert result["pruned"] is False
    assert result["reason"] == "disabled"
    assert db.is_file()


def test_max_bytes_zero_disables(tmp_path: Path) -> None:
    db = _write_fake_checkpoint(tmp_path, main_bytes=10_000)
    result = maybe_reset_checkpoint_db(db, max_bytes=0, enabled=True, cooldown_s=0)
    assert result["pruned"] is False
    assert result["reason"] == "limit_disabled"
    assert db.is_file()


def test_force_resets_even_under_limit(tmp_path: Path) -> None:
    db = _write_fake_checkpoint(tmp_path, main_bytes=10)
    result = maybe_reset_checkpoint_db(db, max_bytes=10_000, enabled=True, force=True, cooldown_s=0)
    assert result["pruned"] is True
    assert not db.exists()


def test_cooldown_skips_second_call(tmp_path: Path) -> None:
    clear_checkpoint_prune_cooldown()
    db = _write_fake_checkpoint(tmp_path / "cooldown_case", main_bytes=1000)
    # First call: no cooldown window so prune always applies (avoids cross-test key bleed).
    first = maybe_reset_checkpoint_db(db, max_bytes=100, enabled=True, cooldown_s=0)
    assert first["pruned"] is True, first
    assert first["size_before"] >= 1000

    # Recreate oversized file immediately; cooldown should skip.
    db.write_bytes(b"z" * 1000)
    second = maybe_reset_checkpoint_db(db, max_bytes=100, enabled=True, cooldown_s=60)
    assert second["pruned"] is False, second
    assert second["reason"] == "cooldown"
    assert db.is_file()


def test_settings_map_to_runtime_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from core.di.runtime_config import (
        HolixRuntimeConfig,
        _checkpoint_max_bytes_from_settings,
    )

    from config import Settings

    assert (
        _checkpoint_max_bytes_from_settings(SimpleNamespace(checkpoint_max_mb=50))
        == 50 * 1024 * 1024
    )
    assert _checkpoint_max_bytes_from_settings(SimpleNamespace(checkpoint_max_mb=0)) == 0

    monkeypatch.setenv("HOLIX_CHECKPOINT_MAX_MB", "12")
    monkeypatch.setenv("HOLIX_CHECKPOINT_AUTO_PRUNE", "false")
    cfg = HolixRuntimeConfig.from_settings(Settings(_env_file=None))
    assert cfg.checkpoint_max_bytes == 12 * 1024 * 1024
    assert cfg.checkpoint_auto_prune is False


@pytest.mark.asyncio
async def test_async_checkpointer_prunes_then_opens(tmp_path: Path) -> None:
    from core.persistence import async_checkpointer

    db = tmp_path / "cp.db"
    db.write_bytes(b"not-a-real-sqlite" * 200)  # oversized garbage
    assert db.stat().st_size > 100

    async with async_checkpointer(
        use_persistent=True,
        db_path=str(db),
        max_bytes=100,
        auto_prune=True,
    ) as cp:
        assert cp is not None
        # After prune, AsyncSqliteSaver recreates a valid empty DB
        assert db.is_file()
        # Must not still be the old garbage payload
        assert db.stat().st_size != len(b"not-a-real-sqlite" * 200)
