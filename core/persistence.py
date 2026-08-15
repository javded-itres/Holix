"""
Persistence — wraps LangGraph checkpointing for Holix.

Uses InMemorySaver for sync/studio entry points. Async graph runs use
AsyncSqliteSaver via async_checkpointer() (required for graph.ainvoke).

checkpoints.db can grow large (full graph state per step). Size-based
auto-reset is configurable via HOLIX_CHECKPOINT_MAX_MB (default 200).
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

logger = logging.getLogger(__name__)

# Default matches Settings.checkpoint_max_mb = 200
DEFAULT_CHECKPOINT_MAX_BYTES = 200 * 1024 * 1024

# Min interval between prune attempts for the same path (avoid log spam /
# thrashing under concurrent graph opens).
_PRUNE_COOLDOWN_S = 30.0
_last_prune_attempt: dict[str, float] = {}


def create_checkpointer(
    use_persistent: bool = False,
    db_path: str | None = None,
):
    """Create an in-memory checkpointer (sync-safe, for Studio / tests).

    Do not use sync SqliteSaver with graph.ainvoke() — use async_checkpointer()
    for persistent SQLite checkpointing.
    """
    if use_persistent and db_path:
        logger.debug(
            "create_checkpointer(use_persistent=True) ignored — "
            "use async_checkpointer() for SQLite with ainvoke"
        )
    checkpointer = InMemorySaver()
    logger.info("Using InMemorySaver for checkpointing")
    return checkpointer


def checkpoint_sidecar_paths(db_path: str | Path) -> list[Path]:
    """Main SQLite file plus WAL/SHM/journal sidecars."""
    path = Path(db_path)
    return [
        path,
        Path(f"{path}-wal"),
        Path(f"{path}-shm"),
        Path(f"{path}-journal"),
    ]


def checkpoint_bundle_size_bytes(db_path: str | Path) -> int:
    """Total on-disk size of checkpoints.db and SQLite sidecars."""
    total = 0
    for p in checkpoint_sidecar_paths(db_path):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def maybe_reset_checkpoint_db(
    db_path: str | Path,
    *,
    max_bytes: int = DEFAULT_CHECKPOINT_MAX_BYTES,
    enabled: bool = True,
    force: bool = False,
    cooldown_s: float = _PRUNE_COOLDOWN_S,
) -> dict[str, Any]:
    """If checkpoints bundle exceeds *max_bytes*, delete and start empty.

    Safe for a live profile: only removes LangGraph graph-state snapshots.
    Does **not** touch conversation memory (memory.db) or LTM (ltm.db).

    Args:
        db_path: Path to checkpoints.db.
        max_bytes: Size threshold (bytes). ``<= 0`` disables.
        enabled: Master switch.
        force: Ignore size/cooldown and always delete if files exist.
        cooldown_s: Skip re-check if we recently attempted prune on this path.

    Returns:
        Dict with keys: pruned, reason, size_before, max_bytes, removed, errors.
    """
    path = Path(db_path)
    key = str(path.resolve()) if path.parent.exists() else str(path)
    result: dict[str, Any] = {
        "pruned": False,
        "reason": "",
        "size_before": 0,
        "max_bytes": max_bytes,
        "removed": [],
        "errors": [],
        "path": str(path),
    }

    if not enabled:
        result["reason"] = "disabled"
        return result
    if max_bytes <= 0 and not force:
        result["reason"] = "limit_disabled"
        return result

    now = time.monotonic()
    if not force and cooldown_s > 0:
        last = _last_prune_attempt.get(key, 0.0)
        if now - last < cooldown_s:
            result["reason"] = "cooldown"
            result["size_before"] = checkpoint_bundle_size_bytes(path)
            return result

    size = checkpoint_bundle_size_bytes(path)
    result["size_before"] = size

    if not force and size <= max_bytes:
        result["reason"] = "under_limit"
        return result

    _last_prune_attempt[key] = now

    removed: list[str] = []
    errors: list[str] = []
    for p in checkpoint_sidecar_paths(path):
        try:
            if p.is_file():
                p.unlink()
                removed.append(str(p))
        except OSError as exc:
            errors.append(f"{p}: {exc}")

    result["removed"] = removed
    result["errors"] = errors
    if removed and not errors:
        result["pruned"] = True
        result["reason"] = "reset"
        logger.warning(
            "LangGraph checkpoints reset: %s was %.1f MiB (limit %.1f MiB); "
            "removed %s. Conversation/LTM memory unchanged.",
            path,
            size / (1024 * 1024),
            max_bytes / (1024 * 1024) if max_bytes > 0 else 0.0,
            ", ".join(Path(r).name for r in removed),
        )
    elif removed and errors:
        # Partial — still count as pruned if main db gone
        main_gone = not path.exists()
        result["pruned"] = main_gone
        result["reason"] = "partial" if not main_gone else "reset"
        logger.warning(
            "LangGraph checkpoints prune partial for %s (size=%.1f MiB): removed=%s errors=%s",
            path,
            size / (1024 * 1024),
            removed,
            errors,
        )
    else:
        result["reason"] = "delete_failed" if errors else "nothing_to_remove"
        if errors:
            logger.warning(
                "LangGraph checkpoints prune failed for %s (size=%.1f MiB): %s",
                path,
                size / (1024 * 1024),
                errors,
            )

    return result


def clear_checkpoint_prune_cooldown() -> None:
    """Test helper: reset prune cooldown state."""
    _last_prune_attempt.clear()


@asynccontextmanager
async def async_checkpointer(
    *,
    use_persistent: bool = False,
    db_path: str | None = None,
    max_bytes: int | None = None,
    auto_prune: bool = True,
) -> AsyncIterator[Any]:
    """Yield a checkpointer suitable for async graph.ainvoke().

    When *use_persistent* and *db_path* are set, may reset checkpoints.db
    if on-disk size exceeds *max_bytes* (see HOLIX_CHECKPOINT_MAX_MB).
    """
    if use_persistent and db_path:
        try:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

            from core.crypto.memory_vault import resolve_memory_sqlite_path
            from core.paths import prepare_sqlite_db_file
            from core.sqlite_util import connect_aiosqlite

            # Resolve path and prune *before* open: oversized/corrupt files must
            # not block prepare_sqlite_db_file.
            resolved = resolve_memory_sqlite_path(db_path)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            limit = DEFAULT_CHECKPOINT_MAX_BYTES if max_bytes is None else int(max_bytes)
            maybe_reset_checkpoint_db(
                resolved,
                max_bytes=limit,
                enabled=bool(auto_prune),
            )
            resolved = prepare_sqlite_db_file(resolved)
            # Own connection: busy wait + WAL so concurrent checkpoints do not
            # raise "database is locked" (default aiosqlite timeout is only 5s).
            async with connect_aiosqlite(resolved) as conn:
                checkpointer = AsyncSqliteSaver(conn)
                await checkpointer.setup()
                logger.info("Using AsyncSqliteSaver at %s", resolved)
                yield checkpointer
                return
        except ImportError:
            logger.warning(
                "langgraph-checkpoint-sqlite or aiosqlite not installed, "
                "falling back to InMemorySaver"
            )
        except Exception as exc:
            logger.warning(
                "AsyncSqliteSaver failed (%s), falling back to InMemorySaver",
                exc,
            )

    yield InMemorySaver()
    logger.info("Using InMemorySaver for checkpointing")


def checkpoint_max_bytes_from_env() -> int:
    """Read HOLIX_CHECKPOINT_MAX_MB from environment (fallback for callers without config)."""
    raw = (
        os.environ.get("HOLIX_CHECKPOINT_MAX_MB") or os.environ.get("CHECKPOINT_MAX_MB") or ""
    ).strip()
    if not raw:
        return DEFAULT_CHECKPOINT_MAX_BYTES
    try:
        mb = int(raw)
    except ValueError:
        return DEFAULT_CHECKPOINT_MAX_BYTES
    if mb <= 0:
        return 0
    return mb * 1024 * 1024
