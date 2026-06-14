"""Bridge from agent tools to MAX outbound file delivery."""

from __future__ import annotations

from integrations.max.client import MaxClient
from integrations.max.outbound import send_outbound_files


class MaxDeliveryBridge:
    """Per-run bridge set in execution context for MAX chat sessions."""

    def __init__(
        self,
        client: MaxClient,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
    ) -> None:
        self._client = client
        self._user_id = user_id
        self._chat_id = chat_id

    async def send_files(
        self,
        paths: list[str],
        *,
        caption: str = "",
    ) -> str:
        return await send_outbound_files(
            self._client,
            paths,
            user_id=self._user_id,
            chat_id=self._chat_id,
            caption=caption,
        )