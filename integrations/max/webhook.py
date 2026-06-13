"""Inbound MAX webhook event handling."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from integrations.max.bot import HelixMaxBot
from integrations.max.client import MaxClient
from integrations.max.config import MaxSettings

logger = logging.getLogger(__name__)


class MaxWebhookHandler:
    def __init__(self, settings: MaxSettings, *, client: MaxClient | None = None) -> None:
        self.settings = settings
        self._bot = HelixMaxBot(settings, profile=settings.profile)
        self._client = client or MaxClient(settings.access_token)
        self._owns_client = client is None
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.close()

    def verify_secret(self, header_value: str | None) -> bool:
        expected = self.settings.webhook_secret.strip()
        if not expected:
            return True
        return bool(header_value) and header_value == expected

    async def handle_update(self, update: dict[str, Any]) -> None:
        async with self._lock:
            await self._bot.handle_update(self._client, update)