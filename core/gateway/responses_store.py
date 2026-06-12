"""Hermes-style stored responses (previous_response_id chains)."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.platform_compat import resolve_holix_home

_MAX_STORED = 100


def _db_path() -> Path:
    path = resolve_holix_home() / "gateway" / "responses.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS responses (
            id TEXT PRIMARY KEY,
            profile TEXT NOT NULL,
            conversation TEXT,
            payload TEXT NOT NULL,
            created_at REAL NOT NULL,
            accessed_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


@dataclass(slots=True)
class StoredResponse:
    id: str
    profile: str
    conversation: str | None
    payload: dict[str, Any]
    created_at: float

    def to_api_dict(self) -> dict[str, Any]:
        out = dict(self.payload)
        out.setdefault("id", self.id)
        out.setdefault("object", "response")
        return out


class ResponsesStore:
    def save(
        self,
        *,
        profile: str,
        payload: dict[str, Any],
        conversation: str | None = None,
        response_id: str | None = None,
    ) -> StoredResponse:
        rid = response_id or f"resp_{uuid.uuid4().hex[:24]}"
        now = time.time()
        conn = _connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO responses (id, profile, conversation, payload, created_at, accessed_at) VALUES (?, ?, ?, ?, ?, ?)",
                (rid, profile, conversation, json.dumps(payload, ensure_ascii=False), now, now),
            )
            self._evict_lru(conn)
            conn.commit()
        finally:
            conn.close()
        return StoredResponse(
            id=rid,
            profile=profile,
            conversation=conversation,
            payload=payload,
            created_at=now,
        )

    def get(self, response_id: str) -> StoredResponse | None:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT id, profile, conversation, payload, created_at FROM responses WHERE id = ?",
                (response_id,),
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE responses SET accessed_at = ? WHERE id = ?",
                (time.time(), response_id),
            )
            conn.commit()
            return StoredResponse(
                id=row["id"],
                profile=row["profile"],
                conversation=row["conversation"],
                payload=json.loads(row["payload"]),
                created_at=row["created_at"],
            )
        finally:
            conn.close()

    def delete(self, response_id: str) -> bool:
        conn = _connect()
        try:
            cur = conn.execute("DELETE FROM responses WHERE id = ?", (response_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def latest_for_conversation(self, profile: str, conversation: str) -> StoredResponse | None:
        conn = _connect()
        try:
            row = conn.execute(
                """
                SELECT id, profile, conversation, payload, created_at
                FROM responses
                WHERE profile = ? AND conversation = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (profile, conversation),
            ).fetchone()
            if row is None:
                return None
            return StoredResponse(
                id=row["id"],
                profile=row["profile"],
                conversation=row["conversation"],
                payload=json.loads(row["payload"]),
                created_at=row["created_at"],
            )
        finally:
            conn.close()

    def _evict_lru(self, conn: sqlite3.Connection) -> None:
        count = conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
        if count <= _MAX_STORED:
            return
        excess = count - _MAX_STORED
        conn.execute(
            """
            DELETE FROM responses WHERE id IN (
                SELECT id FROM responses ORDER BY accessed_at ASC LIMIT ?
            )
            """,
            (excess,),
        )