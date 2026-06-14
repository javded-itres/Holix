"""Keep MAX «typing…» status while the agent is working."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from integrations.max.client import MaxClient

logger = logging.getLogger(__name__)

# MAX clears typing after a short TTL; refresh before it expires.
_DEFAULT_INTERVAL_S = 4.0


class TypingIndicator:
    """Periodically sends ``typing_on`` chat action until stopped."""

    def __init__(
        self,
        client: MaxClient,
        chat_id: int | None,
        *,
        interval_s: float = _DEFAULT_INTERVAL_S,
    ) -> None:
        self._client = client
        self._chat_id = chat_id
        self._interval_s = interval_s
        self._task: asyncio.Task[None] | None = None

    async def _send_typing(self) -> None:
        if self._chat_id is None:
            return
        try:
            await self._client.send_chat_action(self._chat_id, action="typing_on")
        except Exception:
            logger.debug("MAX typing indicator failed (chat_id=%s)", self._chat_id)

    async def _refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval_s)
            await self._send_typing()

    async def start(self) -> None:
        if self._chat_id is None:
            return
        if self._task is not None and not self._task.done():
            return
        await self._send_typing()
        self._task = asyncio.create_task(self._refresh_loop(), name="max-typing")

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