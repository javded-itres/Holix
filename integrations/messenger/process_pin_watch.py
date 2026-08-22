"""Watch pinned background processes and unpin when the OS process dies."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from core.platform_compat import is_process_alive
from core.runtime.background_process import get_background_process_registry

from integrations.messenger.process_pins import iter_platform_pins

logger = logging.getLogger(__name__)

UnpinFn = Callable[[str, str, dict[str, Any]], Awaitable[None]]


def process_is_alive(process_id: str, rec: dict[str, Any]) -> bool:
    registry = get_background_process_registry()
    live = registry.get(process_id)
    if live is not None:
        return bool(live.is_running())
    os_pid = rec.get("os_pid")
    try:
        pid = int(os_pid or 0)
    except (TypeError, ValueError):
        pid = 0
    if pid <= 0:
        return False
    return bool(is_process_alive(pid))


async def reap_dead_pins(
    *,
    bot_profile: str,
    platform: str,
    unpin: UnpinFn,
) -> int:
    """Unpin notices whose OS process is gone. Returns number of reaps."""
    n = 0
    for chat_id, process_id, rec in iter_platform_pins(bot_profile, platform):
        if process_is_alive(process_id, rec):
            continue
        try:
            await unpin(chat_id, process_id, rec)
            n += 1
        except Exception:
            logger.debug("failed to unpin dead %s process %s", platform, process_id, exc_info=True)
    return n


async def watch_dead_pins(
    *,
    bot_profile: str,
    platform: str,
    unpin: UnpinFn,
    interval_s: float = 8.0,
) -> None:
    delay = max(2.0, float(interval_s))
    while True:
        try:
            await reap_dead_pins(bot_profile=bot_profile, platform=platform, unpin=unpin)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("process pin watch failed", exc_info=True)
        await asyncio.sleep(delay)
