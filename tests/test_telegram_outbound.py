"""Telegram outbound file delivery."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from integrations.telegram.delivery_bridge import TelegramDeliveryBridge
from integrations.telegram.outbound import (
    _album_batches,
    classify_outbound_file,
    prepare_outbound_files,
    send_outbound_files,
)


def test_classify_outbound_file(tmp_path: Path) -> None:
    assert classify_outbound_file(tmp_path / "a.jpg") == "photo"
    assert classify_outbound_file(tmp_path / "clip.mp4") == "video"
    assert classify_outbound_file(tmp_path / "song.mp3") == "audio"
    assert classify_outbound_file(tmp_path / "report.pdf") == "document"


def test_album_batches_groups_visual_and_documents() -> None:
    from integrations.telegram.outbound import OutboundFile

    files = [
        OutboundFile(Path("/a.jpg"), "photo", 10, "image/jpeg"),
        OutboundFile(Path("/b.png"), "photo", 20, "image/png"),
        OutboundFile(Path("/c.pdf"), "document", 30, "application/pdf"),
        OutboundFile(Path("/d.docx"), "document", 40, "application/vnd"),
    ]
    batches = _album_batches(files)
    assert len(batches) == 2
    assert {b[0].kind for b in batches} == {"photo", "document"}
    assert sum(len(b) for b in batches) == 4


def test_prepare_outbound_files_rejects_missing(tmp_path: Path) -> None:
    ok = tmp_path / "exists.txt"
    ok.write_text("hi", encoding="utf-8")
    files, errors = prepare_outbound_files([str(ok), str(tmp_path / "nope.txt")])
    assert len(files) == 1
    assert files[0].path == ok.resolve()
    assert any("not found" in e for e in errors)


@pytest.mark.asyncio
async def test_send_outbound_single_photo(tmp_path: Path) -> None:
    photo = tmp_path / "shot.png"
    photo.write_bytes(b"\x89PNG\r\n\x1a\n")

    bot = MagicMock()
    bot.send_photo = AsyncMock()

    result = await send_outbound_files(bot, 42, [str(photo)], caption="here")
    assert "Sent 1 file" in result
    bot.send_photo.assert_awaited_once()
    assert bot.send_photo.await_args.args[0] == 42
    assert bot.send_photo.await_args.kwargs.get("caption") == "here"


@pytest.mark.asyncio
async def test_send_outbound_media_group_for_multiple_photos(tmp_path: Path) -> None:
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    a.write_bytes(b"jpeg-a")
    b.write_bytes(b"jpeg-b")

    bot = MagicMock()
    bot.send_media_group = AsyncMock()

    result = await send_outbound_files(bot, 7, [str(a), str(b)], caption="pair")
    assert "album: 2 files" in result
    bot.send_media_group.assert_awaited_once()
    media = bot.send_media_group.await_args.args[1]
    assert len(media) == 2


@pytest.mark.asyncio
async def test_send_outbound_document_single(tmp_path: Path) -> None:
    doc = tmp_path / "notes.txt"
    doc.write_text("hello", encoding="utf-8")

    bot = MagicMock()
    bot.send_document = AsyncMock()

    result = await send_outbound_files(bot, 1, [str(doc)])
    assert "Sent 1 file" in result
    bot.send_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_delivery_bridge_delegates_to_outbound(tmp_path: Path) -> None:
    doc = tmp_path / "out.pdf"
    doc.write_bytes(b"%PDF-1.4")

    bot = MagicMock()
    bot.send_document = AsyncMock()
    bridge = TelegramDeliveryBridge(bot, 99)

    result = await bridge.send_files([str(doc)], caption="report")
    assert "Sent 1 file" in result
    bot.send_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_chat_files_tool_uses_bridge(tmp_path: Path) -> None:
    from core.tools.execution_context import (
        chat_delivery_scope,
        reset_chat_delivery_scope,
    )
    from core.tools.send_chat_files import SendChatFilesTool

    path = tmp_path / "data.csv"
    path.write_text("a,b\n1,2", encoding="utf-8")

    bot = MagicMock()
    bot.send_document = AsyncMock()
    bridge = TelegramDeliveryBridge(bot, 5)
    token = chat_delivery_scope(bridge)
    try:
        tool = SendChatFilesTool()
        result = await tool.execute(paths=[str(path)], caption="csv")
        assert "Sent 1 file" in result
    finally:
        reset_chat_delivery_scope(token)


@pytest.mark.asyncio
async def test_send_chat_files_tool_without_bridge() -> None:
    from core.tools.send_chat_files import SendChatFilesTool

    tool = SendChatFilesTool()
    result = await tool.execute(paths=["/tmp/x.txt"])
    assert "only available in Telegram" in result