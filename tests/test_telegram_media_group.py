"""Telegram media group (album) buffering."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from integrations.telegram.file_handler import SavedTelegramFile, format_files_preview
from integrations.telegram.media_group import MediaGroupBuffer, PendingAttachment


@pytest.mark.asyncio
async def test_media_group_buffer_collects_items_before_flush() -> None:
    buffer = MediaGroupBuffer(delay_sec=0.15)
    flushed: list[list[str]] = []

    async def on_flush(batch) -> None:
        flushed.append([item.file_name for item in batch.items])

    item_a = PendingAttachment("id1", "a.jpg", "image/jpeg", 100)
    item_b = PendingAttachment("id2", "b.jpg", "image/jpeg", 200)

    await buffer.add(
        chat_id=1,
        user_id=9,
        media_group_id="grp1",
        item=item_a,
        caption="compare",
        on_flush=on_flush,
    )
    await buffer.add(
        chat_id=1,
        user_id=9,
        media_group_id="grp1",
        item=item_b,
        on_flush=on_flush,
    )

    await asyncio.sleep(0.35)
    assert flushed == [["a.jpg", "b.jpg"]]


@pytest.mark.asyncio
async def test_media_group_buffer_keeps_caption_from_first_message() -> None:
    buffer = MediaGroupBuffer(delay_sec=0.1)
    seen_caption = ""

    async def on_flush(batch) -> None:
        nonlocal seen_caption
        seen_caption = batch.caption

    await buffer.add(
        chat_id=2,
        user_id=1,
        media_group_id="g2",
        item=PendingAttachment("x", "doc.pdf", "application/pdf", 50),
        caption="Сводка по файлам",
        on_flush=on_flush,
    )
    await buffer.add(
        chat_id=2,
        user_id=1,
        media_group_id="g2",
        item=PendingAttachment("y", "doc2.pdf", "application/pdf", 60),
        caption="",
        on_flush=on_flush,
    )

    await asyncio.sleep(0.25)
    assert seen_caption == "Сводка по файлам"


def test_format_files_preview_lists_multiple() -> None:
    files = [
        SavedTelegramFile(
            path=Path("/tmp/a.jpg"),
            original_name="a.jpg",
            mime_type="image/jpeg",
            kind="image",
            size_bytes=2048,
            description="cat",
        ),
        SavedTelegramFile(
            path=Path("/tmp/b.pdf"),
            original_name="b.pdf",
            mime_type="application/pdf",
            kind="document",
            size_bytes=4096,
            description="report",
        ),
    ]
    text = format_files_preview(files)
    assert "Сохранено 2" in text
    assert "a.jpg" in text
    assert "b.pdf" in text
    assert "cat" in text