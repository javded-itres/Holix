import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Any

import aiosqlite

from config import settings
from core.paths import resolve_api_keys_db_path
from core.sqlite_util import connect_aiosqlite


class APIKeyManager:
    """Manages API keys for authentication."""

    def __init__(self, db_path: str | None = None):
        self.db_path = resolve_api_keys_db_path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def initialize_db(self) -> None:
        async with connect_aiosqlite(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_hash TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_used DATETIME,
                    is_active BOOLEAN DEFAULT 1,
                    rate_limit INTEGER DEFAULT 100,
                    permissions TEXT DEFAULT 'read,write',
                    allowed_profiles TEXT
                )
                """
            )
            # Migrate older DBs that predate allowed_profiles.
            try:
                await db.execute(
                    "ALTER TABLE api_keys ADD COLUMN allowed_profiles TEXT"
                )
            except Exception:
                pass  # column already exists
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_key_hash ON api_keys(key_hash)"
            )
            await db.commit()

    def generate_api_key(self) -> str:
        return f"hx_{secrets.token_urlsafe(32)}"

    def _pepper(self) -> str:
        pepper = settings.api_key_pepper.strip()
        if not pepper:
            raise RuntimeError(
                "HOLIX_API_KEY_PEPPER must be set for API key hashing"
            )
        return pepper

    def hash_key(self, api_key: str) -> str:
        """HMAC-SHA256 with server pepper (deterministic API key lookup)."""
        return hmac.new(
            self._pepper().encode(),
            api_key.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def create_api_key(
        self,
        name: str,
        permissions: str = "read,write",
        rate_limit: int | None = None,
        allowed_profiles: str | list[str] | None = None,
    ) -> str:
        api_key = self.generate_api_key()
        key_hash = self.hash_key(api_key)
        limit = rate_limit if rate_limit is not None else settings.rate_limit_rpm
        if allowed_profiles is None:
            profiles_raw = None
        elif isinstance(allowed_profiles, str):
            profiles_raw = allowed_profiles.strip() or None
        else:
            profiles_raw = ",".join(
                str(p).strip() for p in allowed_profiles if str(p).strip()
            ) or None

        async with connect_aiosqlite(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO api_keys (key_hash, name, permissions, rate_limit, allowed_profiles)
                VALUES (?, ?, ?, ?, ?)
                """,
                (key_hash, name, permissions, limit, profiles_raw),
            )
            await db.commit()

        return api_key

    async def validate_api_key(self, api_key: str) -> dict[str, Any] | None:
        if not api_key:
            return None

        key_hash = self.hash_key(api_key)

        async with connect_aiosqlite(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, name, permissions, rate_limit, is_active, last_used,
                       allowed_profiles
                FROM api_keys
                WHERE key_hash = ? AND is_active = 1
                """,
                (key_hash,),
            )
            row = await cursor.fetchone()
            if row:
                await db.execute(
                    "UPDATE api_keys SET last_used = CURRENT_TIMESTAMP WHERE key_hash = ?",
                    (key_hash,),
                )
                await db.commit()
                from core.security.permissions import parse_allowed_profiles

                raw_profiles = None
                try:
                    raw_profiles = row["allowed_profiles"]
                except (KeyError, IndexError):
                    raw_profiles = None
                return {
                    "id": row["id"],
                    "name": row["name"],
                    "permissions": row["permissions"].split(","),
                    "rate_limit": row["rate_limit"],
                    "last_used": row["last_used"],
                    "allowed_profiles": parse_allowed_profiles(raw_profiles),
                }
        return None

    async def revoke_api_key(self, api_key: str) -> bool:
        key_hash = self.hash_key(api_key)
        async with connect_aiosqlite(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE api_keys SET is_active = 0 WHERE key_hash = ?",
                (key_hash,),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def list_api_keys(self) -> list:
        async with connect_aiosqlite(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, name, created_at, last_used, is_active, permissions,
                       rate_limit, allowed_profiles
                FROM api_keys
                ORDER BY created_at DESC
                """
            )
            rows = await cursor.fetchall()
            out = []
            for row in rows:
                try:
                    ap = row["allowed_profiles"]
                except (KeyError, IndexError):
                    ap = None
                out.append(
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "created_at": row["created_at"],
                        "last_used": row["last_used"],
                        "is_active": bool(row["is_active"]),
                        "permissions": row["permissions"],
                        "rate_limit": row["rate_limit"],
                        "allowed_profiles": ap,
                    }
                )
            return out


class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self) -> None:
        self.requests: dict[str, list] = {}

    def check_rate_limit(self, key: str, limit: int, window: int = 60) -> bool:
        now = datetime.now()
        cutoff = now - timedelta(seconds=window)

        if key in self.requests:
            self.requests[key] = [t for t in self.requests[key] if t > cutoff]
        else:
            self.requests[key] = []

        if len(self.requests[key]) >= limit:
            return False

        self.requests[key].append(now)
        return True