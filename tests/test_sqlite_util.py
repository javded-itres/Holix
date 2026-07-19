"""SQLite concurrency helpers (busy timeout + WAL)."""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

from core.sqlite_util import connect_aiosqlite, connect_sqlite


def test_connect_sqlite_sets_busy_timeout_and_wal(tmp_path):
    db = tmp_path / "t.db"
    conn = connect_sqlite(db)
    try:
        busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert int(busy) >= 30_000
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"
    finally:
        conn.close()


def test_connect_sqlite_wal_false_skips_journal_change(tmp_path):
    db = tmp_path / "user.db"
    # Create with default delete journal first
    raw = sqlite3.connect(str(db))
    raw.execute("CREATE TABLE t (id INTEGER)")
    raw.commit()
    raw.close()

    conn = connect_sqlite(db, wal=False)
    try:
        busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert int(busy) >= 30_000
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_connect_aiosqlite_concurrent_writes(tmp_path):
    db = tmp_path / "mem.db"

    async with connect_aiosqlite(db) as conn:
        await conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, body TEXT)")
        await conn.commit()

    async def writer(n: int) -> None:
        async with connect_aiosqlite(db) as conn:
            for i in range(20):
                await conn.execute(
                    "INSERT INTO messages (body) VALUES (?)",
                    (f"w{n}-{i}",),
                )
                await conn.commit()

    await asyncio.gather(*(writer(i) for i in range(4)))

    async with connect_aiosqlite(db) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM messages")
        row = await cur.fetchone()
        assert row[0] == 80
