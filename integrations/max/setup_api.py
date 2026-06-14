"""MAX API helpers for interactive setup."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from integrations.max.client import MaxApiError, MaxClient
from integrations.max.models import user_id_from_update


async def verify_access_token(token: str) -> dict[str, Any]:
    async with MaxClient(token) as client:
        return await client.get_me()


async def wait_for_max_user(
    token: str,
    *,
    timeout_s: float = 90.0,
    poll_interval_s: float = 2.0,
) -> int | None:
    """Return first user id from bot updates (after user starts the bot in MAX)."""
    marker: int | None = None
    deadline = time.monotonic() + timeout_s
    async with MaxClient(token) as client:
        while time.monotonic() < deadline:
            try:
                payload = await client.get_updates(
                    marker=marker,
                    limit=50,
                    timeout=0,
                    types=["message_created", "bot_started"],
                )
            except MaxApiError:
                await asyncio.sleep(poll_interval_s)
                continue
            updates = payload.get("updates")
            if not isinstance(updates, list):
                await asyncio.sleep(poll_interval_s)
                continue
            next_marker = payload.get("marker")
            if isinstance(next_marker, int):
                marker = next_marker
            for update in updates:
                if not isinstance(update, dict):
                    continue
                uid = user_id_from_update(update)
                if uid is not None:
                    return uid
            await asyncio.sleep(poll_interval_s)
    return None