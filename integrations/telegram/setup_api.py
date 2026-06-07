"""Telegram Bot API helpers for interactive setup."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp


class TelegramApiError(Exception):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


async def _api_request(token: str, method: str, **params: Any) -> Any:
    url = f"https://api.telegram.org/bot{token}/{method}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params or None, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            data = await resp.json()
    if not data.get("ok"):
        desc = data.get("description", "Telegram API error")
        raise TelegramApiError(str(desc), status=data.get("error_code"))
    return data.get("result")


async def _api_get(token: str, method: str, **params: Any) -> dict[str, Any]:
    result = await _api_request(token, method, **params)
    return result if isinstance(result, dict) else {}


async def verify_bot_token(token: str) -> dict[str, Any]:
    """Return getMe payload (id, username, first_name, …)."""
    return await _api_get(token, "getMe")


async def wait_for_telegram_user(
    token: str,
    *,
    timeout_s: float = 90.0,
    poll_interval_s: float = 2.0,
) -> int | None:
    """Return first user id from bot updates (after user sends /start)."""
    import time

    offset: int | None = None
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        params: dict[str, Any] = {"timeout": 0}
        if offset is not None:
            params["offset"] = offset
        try:
            result = await _api_request(token, "getUpdates", **params)
        except TelegramApiError:
            await asyncio.sleep(poll_interval_s)
            continue
        if not isinstance(result, list):
            await asyncio.sleep(poll_interval_s)
            continue
        for update in result:
            uid = _user_id_from_update(update)
            upd_id = update.get("update_id")
            if isinstance(upd_id, int):
                offset = upd_id + 1
            if uid is not None:
                return uid
        await asyncio.sleep(poll_interval_s)
    return None


def _user_id_from_update(update: dict[str, Any]) -> int | None:
    for key in ("message", "edited_message", "callback_query"):
        block = update.get(key)
        if not isinstance(block, dict):
            continue
        if key == "callback_query":
            user = block.get("from")
        else:
            user = block.get("from")
        if isinstance(user, dict) and isinstance(user.get("id"), int):
            return int(user["id"])
    return None