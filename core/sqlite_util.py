"""Shared SQLite open helpers (busy timeout + WAL for concurrent Studio/agent use)."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

# Wait for locks instead of failing immediately under concurrent agent/subagent writes.
DEFAULT_BUSY_TIMEOUT_S = 30.0


def apply_sqlite_pragmas(
    conn: sqlite3.Connection,
    *,
    wal: bool = True,
    busy_timeout_s: float = DEFAULT_BUSY_TIMEOUT_S,
) -> None:
    """Apply concurrency-friendly PRAGMAs on an open sync connection."""
    ms = max(0, int(busy_timeout_s * 1000))
    conn.execute(f"PRAGMA busy_timeout={ms}")
    if wal:
        # WAL allows readers during a writer; NORMAL is safe with WAL.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")


def connect_sqlite(
    path: str | Path,
    *,
    timeout: float = DEFAULT_BUSY_TIMEOUT_S,
    check_same_thread: bool = True,
    wal: bool = True,
    **kwargs: Any,
) -> sqlite3.Connection:
    """Open a sync SQLite connection with busy wait and optional WAL."""
    conn = sqlite3.connect(
        str(path),
        timeout=timeout,
        check_same_thread=check_same_thread,
        **kwargs,
    )
    apply_sqlite_pragmas(conn, wal=wal, busy_timeout_s=timeout)
    return conn


async def apply_aiosqlite_pragmas(
    db: aiosqlite.Connection,
    *,
    wal: bool = True,
    busy_timeout_s: float = DEFAULT_BUSY_TIMEOUT_S,
) -> None:
    """Apply concurrency-friendly PRAGMAs on an open aiosqlite connection."""
    ms = max(0, int(busy_timeout_s * 1000))
    await db.execute(f"PRAGMA busy_timeout={ms}")
    if wal:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")


@asynccontextmanager
async def connect_aiosqlite(
    path: str | Path,
    *,
    timeout: float = DEFAULT_BUSY_TIMEOUT_S,
    wal: bool = True,
    **kwargs: Any,
) -> AsyncIterator[aiosqlite.Connection]:
    """Open an aiosqlite connection with busy wait and optional WAL."""
    db = await aiosqlite.connect(str(path), timeout=timeout, **kwargs)
    try:
        await apply_aiosqlite_pragmas(db, wal=wal, busy_timeout_s=timeout)
        yield db
    finally:
        await db.close()
