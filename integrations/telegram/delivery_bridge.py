"""Bridge from agent tools to Telegram outbound file delivery."""

from __future__ import annotations

from typing import Any

from integrations.telegram.outbound import send_outbound_files


class TelegramDeliveryBridge:
    """Per-run bridge set in execution context for Telegram chat sessions."""

    def __init__(self, bot: Any, chat_id: int) -> None:
        self._bot = bot
        self._chat_id = chat_id

    async def send_files(
        self,
        paths: list[str],
        *,
        caption: str = "",
    ) -> str:
        return await send_outbound_files(
            self._bot,
            self._chat_id,
            paths,
            caption=caption,
        )