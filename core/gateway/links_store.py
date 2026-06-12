"""SQLite store for Holix Link pairing codes and active links."""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from integrations.link.protocol import LinkPermissions

from core.platform_compat import resolve_holix_home


def _db_path() -> Path:
    path = resolve_holix_home() / "gateway" / "links.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pair_codes (
            code TEXT PRIMARY KEY,
            profile TEXT NOT NULL,
            expires_at REAL NOT NULL,
            created_at REAL NOT NULL,
            created_by TEXT,
            used INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS links (
            link_id TEXT PRIMARY KEY,
            profile TEXT NOT NULL,
            folder_portable TEXT NOT NULL,
            device_public_key_b64 TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            permissions_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            last_connected_at REAL
        )
        """
    )
    conn.commit()
    return conn


def _code_part() -> str:
    return secrets.token_hex(2).upper()[:4]


def _generate_pair_code() -> str:
    return f"LINK-{_code_part()}-{_code_part()}"


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


@dataclass(slots=True)
class PairCodeRecord:
    code: str
    profile: str
    expires_at: float
    created_at: float
    created_by: str | None
    used: bool


@dataclass(slots=True)
class LinkRecord:
    link_id: str
    profile: str
    folder_portable: str
    device_public_key_b64: str
    status: str
    permissions: LinkPermissions
    created_at: float
    last_connected_at: float | None

    def permissions_json(self) -> str:
        return json.dumps(self.permissions.model_dump(), ensure_ascii=False)


class LinksStore:
    def create_pair_code(
        self,
        *,
        profile: str,
        ttl_seconds: int,
        created_by: str | None = None,
    ) -> PairCodeRecord:
        now = time.time()
        expires = now + ttl_seconds
        code = _generate_pair_code()
        conn = _connect()
        try:
            while True:
                try:
                    conn.execute(
                        """
                        INSERT INTO pair_codes (code, profile, expires_at, created_at, created_by, used)
                        VALUES (?, ?, ?, ?, ?, 0)
                        """,
                        (code, profile, expires, now, created_by),
                    )
                    conn.commit()
                    break
                except sqlite3.IntegrityError:
                    code = _generate_pair_code()
        finally:
            conn.close()
        return PairCodeRecord(
            code=code,
            profile=profile,
            expires_at=expires,
            created_at=now,
            created_by=created_by,
            used=False,
        )

    def get_pair_code(self, code: str) -> PairCodeRecord | None:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT code, profile, expires_at, created_at, created_by, used FROM pair_codes WHERE code = ?",
                (code.strip().upper(),),
            ).fetchone()
            if row is None:
                return None
            return PairCodeRecord(
                code=row["code"],
                profile=row["profile"],
                expires_at=row["expires_at"],
                created_at=row["created_at"],
                created_by=row["created_by"],
                used=bool(row["used"]),
            )
        finally:
            conn.close()

    def mark_pair_code_used(self, code: str) -> None:
        conn = _connect()
        try:
            conn.execute("UPDATE pair_codes SET used = 1 WHERE code = ?", (code,))
            conn.commit()
        finally:
            conn.close()

    def create_link(
        self,
        *,
        profile: str,
        folder_portable: str,
        device_public_key_b64: str,
        permissions: LinkPermissions,
    ) -> LinkRecord:
        link_id = f"link_{uuid.uuid4().hex[:16]}"
        now = time.time()
        perms_json = json.dumps(permissions.model_dump(), ensure_ascii=False)
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO links (
                    link_id, profile, folder_portable, device_public_key_b64,
                    status, permissions_json, created_at, last_connected_at
                ) VALUES (?, ?, ?, ?, 'active', ?, ?, NULL)
                """,
                (link_id, profile, folder_portable, device_public_key_b64, perms_json, now),
            )
            conn.commit()
        finally:
            conn.close()
        return LinkRecord(
            link_id=link_id,
            profile=profile,
            folder_portable=folder_portable,
            device_public_key_b64=device_public_key_b64,
            status="active",
            permissions=permissions,
            created_at=now,
            last_connected_at=None,
        )

    def get_link(self, link_id: str) -> LinkRecord | None:
        conn = _connect()
        try:
            row = conn.execute(
                """
                SELECT link_id, profile, folder_portable, device_public_key_b64,
                       status, permissions_json, created_at, last_connected_at
                FROM links WHERE link_id = ?
                """,
                (link_id,),
            ).fetchone()
            if row is None:
                return None
            return _row_to_link(row)
        finally:
            conn.close()

    def list_links(self, *, profile: str | None = None, status: str | None = "active") -> list[LinkRecord]:
        conn = _connect()
        try:
            query = "SELECT * FROM links WHERE 1=1"
            params: list[object] = []
            if profile:
                query += " AND profile = ?"
                params.append(profile)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, params).fetchall()
            return [_row_to_link(row) for row in rows]
        finally:
            conn.close()

    def count_active_links(self, profile: str) -> int:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM links WHERE profile = ? AND status = 'active'",
                (profile,),
            ).fetchone()
            return int(row["cnt"]) if row else 0
        finally:
            conn.close()

    def revoke_link(self, link_id: str) -> bool:
        conn = _connect()
        try:
            cur = conn.execute(
                "UPDATE links SET status = 'revoked' WHERE link_id = ? AND status = 'active'",
                (link_id,),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def set_connected(self, link_id: str, *, connected: bool) -> None:
        conn = _connect()
        try:
            ts = time.time() if connected else None
            conn.execute(
                "UPDATE links SET last_connected_at = ? WHERE link_id = ?",
                (ts, link_id),
            )
            conn.commit()
        finally:
            conn.close()

    def purge_expired_pair_codes(self) -> int:
        conn = _connect()
        try:
            cur = conn.execute("DELETE FROM pair_codes WHERE expires_at < ?", (time.time(),))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()


def _row_to_link(row: sqlite3.Row) -> LinkRecord:
    perms = LinkPermissions.model_validate(json.loads(row["permissions_json"]))
    return LinkRecord(
        link_id=row["link_id"],
        profile=row["profile"],
        folder_portable=row["folder_portable"],
        device_public_key_b64=row["device_public_key_b64"],
        status=row["status"],
        permissions=perms,
        created_at=row["created_at"],
        last_connected_at=row["last_connected_at"],
    )


def pair_code_expires_iso(record: PairCodeRecord) -> str:
    return _iso(record.expires_at)


def link_connected_iso(record: LinkRecord) -> str | None:
    if record.last_connected_at is None:
        return None
    return _iso(record.last_connected_at)