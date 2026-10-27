"""Send one Telegram message, retrying only while Telegram has not accepted it."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter

logger = logging.getLogger(__name__)

SEND_ATTEMPTS = 5


class SendMaybeDelivered(Exception):
    """The request may already be in the chat. Another send would duplicate it."""


def _not_accepted(exc: TelegramNetworkError) -> bool:
    """True when the socket failed before Telegram could store the message."""
    cause = exc.__cause__
    try:
        import aiohttp
    except ImportError:
        return False
    if isinstance(cause, aiohttp.ConnectionTimeoutError):
        return True
    return isinstance(cause, aiohttp.ClientConnectorError)


async def send_message_once(bot: Any, *args: Any, **kwargs: Any) -> Any:
    """Call ``bot.send_message`` up to five times. Return the first accepted message."""
    last: BaseException | None = None
    for attempt in range(SEND_ATTEMPTS):
        try:
            return await bot.send_message(*args, **kwargs)
        except TelegramRetryAfter as exc:
            last = exc
            if attempt + 1 >= SEND_ATTEMPTS:
                raise
            await asyncio.sleep(min(max(int(exc.retry_after), 0), 30))
        except TelegramNetworkError as exc:
            if not _not_accepted(exc):
                raise SendMaybeDelivered(str(exc)) from exc
            last = exc
            if attempt + 1 >= SEND_ATTEMPTS:
                raise
            logger.warning(
                "telegram send retry %s/%s after %s",
                attempt + 1,
                SEND_ATTEMPTS,
                type(exc.__cause__).__name__ if exc.__cause__ else type(exc).__name__,
            )
            await asyncio.sleep(0.4 * (attempt + 1))
    raise last or RuntimeError("telegram send failed")
