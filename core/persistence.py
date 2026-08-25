"""
Persistence — wraps LangGraph checkpointing for Holix.

Uses InMemorySaver for sync/studio entry points. Async graph runs use
AsyncSqliteSaver via async_checkpointer() (required for graph.ainvoke).

Overlapping graphs in one process (Telegram + sub-agents, Studio host
sessions) share a single aiosqlite connection so SQLite is not opened
once per in-flight turn. Cross-process writers still use WAL + busy wait.

checkpoints.db can grow large (full graph state per step). Size-based
auto-reset is configurable via HOLIX_CHECKPOINT_MAX_MB (default 200).
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

logger = logging.getLogger(__name__)

# Default matches Settings.checkpoint_max_mb = 200
DEFAULT_CHECKPOINT_MAX_BYTES = 200 * 1024 * 1024

# Wait longer than aiosqlite's 5s default: overlapping Studio/Telegram
# checkpoint blobs can occupy the writer lock for tens of seconds.
CHECKPOINT_BUSY_TIMEOUT_S = 60.0

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


@dataclass
class _SharedCheckpointer:
    conn: Any
    saver: Any
    refs: int = 0


# One SQLite connection per event loop + path. AsyncSqliteSaver.lock then
# serializes aput/aget instead of N connections racing on checkpoints.db.
_shared: dict[tuple[int, str], _SharedCheckpointer] = {}
_loop_locks: dict[int, asyncio.Lock] = {}
_shared_meta = threading.Lock()


def _running_loop_id() -> int:
    return id(asyncio.get_running_loop())


def _pool_lock() -> asyncio.Lock:
    lid = _running_loop_id()
    with _shared_meta:
        lock = _loop_locks.get(lid)
        if lock is None:
            lock = asyncio.Lock()
            _loop_locks[lid] = lock
        return lock


async def close_shared_checkpointers() -> None:
    """Close cached checkpoint connections for the current event loop."""
    async with _pool_lock():
        lid = _running_loop_id()
        for key in [k for k in _shared if k[0] == lid]:
            holder = _shared.pop(key)
            try:
                await holder.conn.close()
            except Exception:
                logger.debug("close shared checkpointer failed", exc_info=True)


async def _acquire_shared_sqlite_saver(
    db_path: str,
    *,
    max_bytes: int,
    auto_prune: bool,
) -> tuple[tuple[int, str], Any]:
    """Open or reuse the process/loop AsyncSqliteSaver for *db_path*.

    Returns ``(cache_key, saver)``. Caller must ``_release_shared_sqlite_saver``.
    """
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    from core.crypto.memory_vault import resolve_memory_sqlite_path
    from core.paths import prepare_sqlite_db_file
    from core.sqlite_util import apply_aiosqlite_pragmas

    resolved = resolve_memory_sqlite_path(db_path)
    key = (_running_loop_id(), str(resolved))
    async with _pool_lock():
        holder = _shared.get(key)
        if holder is None:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            maybe_reset_checkpoint_db(
                resolved,
                max_bytes=max_bytes,
                enabled=bool(auto_prune),
            )
            open_path = prepare_sqlite_db_file(resolved)
            # isolation_level=None (autocommit): LangGraph SELECTs never
            # COMMIT, so a deferred txn would hold a read lock across the
            # whole node and deadlock writers.
            conn = await aiosqlite.connect(
                str(open_path),
                timeout=CHECKPOINT_BUSY_TIMEOUT_S,
                isolation_level=None,
            )
            try:
                await apply_aiosqlite_pragmas(
                    conn,
                    wal=True,
                    busy_timeout_s=CHECKPOINT_BUSY_TIMEOUT_S,
                )
                checkpointer = AsyncSqliteSaver(conn)
                await checkpointer.setup()
            except Exception:
                await conn.close()
                raise
            holder = _SharedCheckpointer(conn=conn, saver=checkpointer)
            _shared[key] = holder
            logger.info("Using AsyncSqliteSaver at %s", open_path)
        else:
            logger.debug(
                "Reusing shared AsyncSqliteSaver at %s (refs=%s)",
                resolved,
                holder.refs,
            )
        holder.refs += 1
        return key, holder.saver


async def _release_shared_sqlite_saver(key: tuple[int, str]) -> None:
    async with _pool_lock():
        holder = _shared.get(key)
        if holder is None:
            return
        holder.refs = max(0, holder.refs - 1)
        if holder.refs == 0:
            _shared.pop(key, None)
            try:
                await holder.conn.close()
            except Exception:
                logger.debug("close shared checkpointer failed", exc_info=True)


@asynccontextmanager
async def async_checkpointer(
    *,
    use_persistent: bool = False,
    db_path: str | None = None,
    max_bytes: int | None = None,
    auto_prune: bool = True,
) -> AsyncIterator[Any]:
    """Yield a checkpointer suitable for async graph.ainvoke().

    When *use_persistent* and *db_path* are set, overlapping callers share
    one AsyncSqliteSaver (and one aiosqlite connection) per process/loop.
    May reset checkpoints.db if on-disk size exceeds *max_bytes*.
    """
    if use_persistent and db_path:
        limit = DEFAULT_CHECKPOINT_MAX_BYTES if max_bytes is None else int(max_bytes)
        try:
            key, saver = await _acquire_shared_sqlite_saver(
                db_path,
                max_bytes=limit,
                auto_prune=auto_prune,
            )
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
        else:
            try:
                yield saver
            finally:
                await _release_shared_sqlite_saver(key)
            return

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
