"""Resolve Holix profile storage paths (never relative to process CWD)."""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_holix_default_data_dir(profile: str = "default") -> Path:
    """Return ``~/.holix/profiles/<profile>/data`` (or HOLIX_HOME equivalent)."""
    from core.platform_compat import resolve_holix_home

    return (resolve_holix_home() / "profiles" / profile / "data").resolve()


def resolve_profile_data_dir(profile: str | None = None) -> Path:
    """Best-effort profile ``data_dir`` for the active or named profile."""
    try:
        from cli.core import get_current_config, get_current_profile, init_profile

        if profile is None:
            try:
                cfg = get_current_config()
            except Exception:
                cfg = init_profile(get_current_profile())
        else:
            cfg = init_profile(profile)
        if cfg.data_dir:
            return Path(cfg.data_dir).expanduser().resolve()
    except Exception:
        pass
    return resolve_holix_default_data_dir(profile or "default")


def resolve_holix_storage_path(path: str | None, *, default: Path) -> Path:
    """Resolve storage paths under ``HOLIX_HOME`` (never process CWD)."""
    from core.env_loader import init_holix_home
    from core.platform_compat import resolve_holix_home

    init_holix_home()
    raw = (path or "").strip()
    if not raw:
        return default.resolve()
    expanded = Path(raw).expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (resolve_holix_home() / expanded).resolve()


def _rename_blocking_path(path: Path) -> Path | None:
    """Move a file/dir blocking SQLite creation aside; return backup path if moved."""
    if not path.exists():
        return None
    backup = path.with_name(f"{path.name}.holix-bak")
    index = 0
    while backup.exists():
        index += 1
        backup = path.with_name(f"{path.name}.holix-bak{index}")
    try:
        path.rename(backup)
        logger.warning("Moved blocking SQLite path %s -> %s", path, backup)
        return backup
    except OSError as exc:
        logger.error("Cannot move blocking SQLite path %s: %s", path, exc)
        return None


def prepare_sqlite_db_file(path: str | Path) -> Path:
    """Ensure a SQLite file path exists and is openable (not a directory / read-only)."""
    db_path = Path(path).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists() and db_path.is_dir():
        _rename_blocking_path(db_path)

    if db_path.exists() and not os.access(db_path, os.W_OK):
        _rename_blocking_path(db_path)

    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA user_version")
        conn.close()
    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Cannot open SQLite database at {db_path} "
            f"(parent={db_path.parent}, writable={os.access(db_path.parent, os.W_OK)}): {exc}"
        ) from exc
    return db_path


def ensure_sqlite_parent(path: str | Path) -> Path:
    """Backward-compatible alias for :func:`prepare_sqlite_db_file`."""
    return prepare_sqlite_db_file(path)


def ensure_profile_memory_dirs(profile: str) -> None:
    """Ensure SQLite/Chroma memory directories exist for a profile."""
    from cli.core import ProfileManager

    cfg = ProfileManager().load_profile(profile)
    prepare_sqlite_db_file(cfg.memory_db_path)
    prepare_sqlite_db_file(cfg.ltm_db_path)
    prepare_sqlite_db_file(cfg.langgraph_checkpoint_db_path)
    Path(cfg.vector_db_path).expanduser().resolve().mkdir(parents=True, exist_ok=True)


def resolve_api_keys_db_path(path: str | None = None) -> Path:
    """Gateway API key SQLite DB — global under ``HOLIX_HOME``."""
    from config import settings
    from core.platform_compat import resolve_holix_home

    default = resolve_holix_home() / "security" / "api_keys.db"
    return resolve_holix_storage_path(path or settings.api_keys_db_path, default=default)


def memory_paths_from_data_dir(data_dir: str | Path) -> dict[str, str]:
    """Derive memory-related paths under a profile data directory."""
    base = Path(data_dir).expanduser().resolve()
    memory = base / "memory"
    return {
        "ltm_db_path": str(memory / "ltm.db"),
        "langgraph_checkpoint_db_path": str(memory / "checkpoints.db"),
    }


def is_stray_holix_data_dir(path: Path) -> bool:
    """True if ``path`` looks like Holix runtime data leaked into a project tree."""
    if not path.is_dir():
        return False
    markers = (
        path / "memory",
        path / "security",
        path / "skills",
        path / "files",
    )
    return any(m.is_dir() for m in markers)