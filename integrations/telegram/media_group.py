"""Buffer Telegram media groups (albums) before processing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass(slots=True)
class PendingAttachment:
    file_id: str
    file_name: str
    mime_type: str
    file_size: int


@dataclass
class MediaGroupBatch:
    chat_id: int
    user_id: int
    media_group_id: str
    items: list[PendingAttachment] = field(default_factory=list)
    caption: str = ""
    flush_task: asyncio.Task | None = None


FlushCallback = Callable[[MediaGroupBatch], Awaitable[None]]


class MediaGroupBuffer:
    """Collect album items sharing media_group_id, flush after a quiet period."""

    def __init__(self, *, delay_sec: float = 0.8) -> None:
        self._delay_sec = max(0.2, delay_sec)
        self._batches: dict[str, MediaGroupBatch] = {}

    def _key(self, chat_id: int, media_group_id: str) -> str:
        return f"{chat_id}:{media_group_id}"

    async def add(
        self,
        *,
        chat_id: int,
        user_id: int,
        media_group_id: str,
        item: PendingAttachment,
        caption: str = "",
        on_flush: FlushCallback,
    ) -> None:
        key = self._key(chat_id, media_group_id)
        batch = self._batches.get(key)
        if batch is None:
            batch = MediaGroupBatch(
                chat_id=chat_id,
                user_id=user_id,
                media_group_id=media_group_id,
            )
            self._batches[key] = batch

        batch.items.append(item)
        if caption and not batch.caption:
            batch.caption = caption.strip()

        if batch.flush_task and not batch.flush_task.done():
            batch.flush_task.cancel()
            try:
                await batch.flush_task
            except asyncio.CancelledError:
                pass

        batch.flush_task = asyncio.create_task(
            self._flush_later(key, on_flush),
            name=f"tg-media-group-{media_group_id}",
        )

    async def _flush_later(self, key: str, on_flush: FlushCallback) -> None:
        try:
            await asyncio.sleep(self._delay_sec)
            batch = self._batches.pop(key, None)
            if batch and batch.items:
                await on_flush(batch)
        except asyncio.CancelledError:
            raise