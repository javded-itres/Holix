"""Telegram Bot API session for the regular agent.

Production pins ``api.telegram.org`` to an address that often never completes
TCP. When ``127.0.0.1:1443`` accepts a connection, that name resolves to the
local forward and the TLS name stays ``api.telegram.org``.
"""

from __future__ import annotations

import socket
from typing import Any

_FORWARD = ("127.0.0.1", 1443)


def _forward_open() -> bool:
    try:
        with socket.create_connection(_FORWARD, timeout=0.4):
            return True
    except OSError:
        return False


class TelegramForwardResolver:
    """Prefer the local forward. Ordinary DNS is used when the port is closed."""

    def __init__(self) -> None:
        from aiohttp.resolver import DefaultResolver

        self._inner = DefaultResolver()

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: int = socket.AF_INET,
    ) -> list[dict[str, Any]]:
        name = (host or "").rstrip(".").lower()
        if name == "api.telegram.org" and _forward_open():
            return [
                {
                    "hostname": "api.telegram.org",
                    "host": _FORWARD[0],
                    "port": _FORWARD[1],
                    "family": socket.AF_INET,
                    "proto": 0,
                    "flags": socket.AI_NUMERICHOST,
                }
            ]
        return await self._inner.resolve(host, port, family)

    async def close(self) -> None:
        close = getattr(self._inner, "close", None)
        if close is not None:
            await close()


def telegram_bot_session() -> Any:
    """Aiogram session. The forward is chosen on each lookup, not at startup."""
    from aiogram.client.session.aiohttp import AiohttpSession

    session = AiohttpSession()
    session._connector_init["resolver"] = TelegramForwardResolver()
    session._connector_init["use_dns_cache"] = False
    return session
