import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path
import json
import aiosqlite

from config import settings


class APIKeyManager:
    """Manages API keys for authentication."""

    def __init__(self, db_path: str = "data/security/api_keys.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def initialize_db(self):
        """Initialize the API keys database."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_hash TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_used DATETIME,
                    is_active BOOLEAN DEFAULT 1,
                    rate_limit INTEGER DEFAULT 100,
                    permissions TEXT DEFAULT 'read,write'
                )
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_key_hash
                ON api_keys(key_hash)
            """)

            await db.commit()

    def generate_api_key(self) -> str:
        """Generate a new API key.

        Returns:
            New API key string
        """
        return f"hx_{secrets.token_urlsafe(32)}"

    def hash_key(self, api_key: str) -> str:
        """Hash an API key for storage.

        Args:
            api_key: Plain API key

        Returns:
            Hashed key
        """
        return hashlib.sha256(api_key.encode()).hexdigest()

    async def create_api_key(
        self,
        name: str,
        permissions: str = "read,write",
        rate_limit: int = 100
    ) -> str:
        """Create a new API key.

        Args:
            name: Key name/description
            permissions: Comma-separated permissions
            rate_limit: Requests per minute

        Returns:
            Generated API key (save this, it won't be shown again!)
        """
        api_key = self.generate_api_key()
        key_hash = self.hash_key(api_key)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO api_keys (key_hash, name, permissions, rate_limit)
                VALUES (?, ?, ?, ?)
                """,
                (key_hash, name, permissions, rate_limit)
            )
            await db.commit()

        return api_key

    async def validate_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Validate an API key and return its info.

        Args:
            api_key: API key to validate

        Returns:
            Key info if valid, None otherwise
        """
        if not api_key:
            return None

        key_hash = self.hash_key(api_key)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                """
                SELECT id, name, permissions, rate_limit, is_active, last_used
                FROM api_keys
                WHERE key_hash = ? AND is_active = 1
                """,
                (key_hash,)
            )

            row = await cursor.fetchone()

            if not row:
                return None

            # Update last_used
            await db.execute(
                "UPDATE api_keys SET last_used = CURRENT_TIMESTAMP WHERE key_hash = ?",
                (key_hash,)
            )
            await db.commit()

            return {
                "id": row["id"],
                "name": row["name"],
                "permissions": row["permissions"].split(","),
                "rate_limit": row["rate_limit"],
                "last_used": row["last_used"]
            }

    async def revoke_api_key(self, api_key: str) -> bool:
        """Revoke an API key.

        Args:
            api_key: API key to revoke

        Returns:
            True if revoked successfully
        """
        key_hash = self.hash_key(api_key)

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE api_keys SET is_active = 0 WHERE key_hash = ?",
                (key_hash,)
            )
            await db.commit()

            return cursor.rowcount > 0

    async def list_api_keys(self) -> list:
        """List all API keys (without showing actual keys).

        Returns:
            List of API key info
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                """
                SELECT id, name, created_at, last_used, is_active, permissions, rate_limit
                FROM api_keys
                ORDER BY created_at DESC
                """
            )

            rows = await cursor.fetchall()

            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "created_at": row["created_at"],
                    "last_used": row["last_used"],
                    "is_active": bool(row["is_active"]),
                    "permissions": row["permissions"],
                    "rate_limit": row["rate_limit"]
                }
                for row in rows
            ]


# Rate limiting
class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self):
        self.requests: Dict[str, list] = {}

    def check_rate_limit(self, key: str, limit: int, window: int = 60) -> bool:
        """Check if request is within rate limit.

        Args:
            key: Identifier (API key hash, IP, etc.)
            limit: Maximum requests
            window: Time window in seconds

        Returns:
            True if allowed, False if rate limit exceeded
        """
        now = datetime.now()
        cutoff = now - timedelta(seconds=window)

        # Clean old requests
        if key in self.requests:
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if req_time > cutoff
            ]
        else:
            self.requests[key] = []

        # Check limit
        if len(self.requests[key]) >= limit:
            return False

        # Add current request
        self.requests[key].append(now)
        return True
