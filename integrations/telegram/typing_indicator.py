"""Keep Telegram «typing…» status while the agent is working."""

from __future__ import annotations

import asyncio
from typing import Any

# Telegram clears typing after ~5s; refresh earlier.
_DEFAULT_INTERVAL_S = 4.0


class TypingIndicator:
    """Periodically sends ``typing`` chat action until stopped."""

    def __init__(
        self,
        bot: Any,
        chat_id: int,
        *,
        interval_s: float = _DEFAULT_INTERVAL_S,
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._interval_s = interval_s
        self._task: asyncio.Task[None] | None = None

    async def _send_typing(self) -> None:
        try:
            from aiogram.enums import ChatAction

            action = ChatAction.TYPING
        except ImportError:
            action = "typing"
        try:
            await self._bot.send_chat_action(self._chat_id, action)
        except Exception:
            pass

    async def _refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval_s)
            await self._send_typing()

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        await self._send_typing()
        self._task = asyncio.create_task(self._refresh_loop(), name="telegram-typing")

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def __aenter__(self) -> TypingIndicator:
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.stop()