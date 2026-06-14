"""MAX outbound file delivery."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from integrations.max.delivery_bridge import MaxDeliveryBridge
from integrations.max.outbound import (
    classify_outbound_file,
    prepare_outbound_files,
    send_outbound_files,
)


def test_classify_outbound_file(tmp_path: Path) -> None:
    assert classify_outbound_file(tmp_path / "a.jpg") == "image"
    assert classify_outbound_file(tmp_path / "clip.mp4") == "video"
    assert classify_outbound_file(tmp_path / "song.mp3") == "audio"
    assert classify_outbound_file(tmp_path / "report.pdf") == "file"


def test_prepare_outbound_files_rejects_missing(tmp_path: Path) -> None:
    ok = tmp_path / "exists.txt"
    ok.write_text("hi", encoding="utf-8")
    files, errors = prepare_outbound_files([str(ok), str(tmp_path / "nope.txt")])
    assert len(files) == 1
    assert files[0].path == ok.resolve()
    assert any("not found" in e for e in errors)


@pytest.mark.asyncio
async def test_send_outbound_single_image(tmp_path: Path) -> None:
    photo = tmp_path / "shot.png"
    photo.write_bytes(b"\x89PNG\r\n\x1a\n")

    client = MagicMock()
    with patch(
        "integrations.max.outbound.send_file_message",
        new_callable=AsyncMock,
    ) as send_mock:
        result = await send_outbound_files(
            client,
            [str(photo)],
            user_id=42,
            caption="here",
        )

    assert "Sent 1 file" in result
    send_mock.assert_awaited_once()
    assert send_mock.await_args.kwargs.get("user_id") == 42
    assert send_mock.await_args.kwargs.get("caption") == "here"


@pytest.mark.asyncio
async def test_send_outbound_multiple_files(tmp_path: Path) -> None:
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    a.write_bytes(b"jpeg-a")
    b.write_bytes(b"jpeg-b")

    client = MagicMock()
    with patch(
        "integrations.max.outbound.send_file_message",
        new_callable=AsyncMock,
    ) as send_mock:
        result = await send_outbound_files(client, [str(a), str(b)], chat_id=7, caption="pair")

    assert "2 files" in result
    assert send_mock.await_count == 2
    assert send_mock.await_args_list[0].kwargs.get("caption") == "pair"
    assert send_mock.await_args_list[1].kwargs.get("caption") == ""


@pytest.mark.asyncio
async def test_send_outbound_document_single(tmp_path: Path) -> None:
    doc = tmp_path / "notes.txt"
    doc.write_text("hello", encoding="utf-8")

    client = MagicMock()
    with patch(
        "integrations.max.outbound.send_file_message",
        new_callable=AsyncMock,
    ) as send_mock:
        result = await send_outbound_files(client, [str(doc)], user_id=1)

    assert "Sent 1 file" in result
    send_mock.assert_awaited_once()
    assert send_mock.await_args.kwargs.get("upload_type") == "file"


@pytest.mark.asyncio
async def test_delivery_bridge_delegates_to_outbound(tmp_path: Path) -> None:
    doc = tmp_path / "out.pdf"
    doc.write_bytes(b"%PDF-1.4")

    client = MagicMock()
    bridge = MaxDeliveryBridge(client, chat_id=99)

    with patch(
        "integrations.max.delivery_bridge.send_outbound_files",
        new_callable=AsyncMock,
        return_value="Sent 1 file(s) to chat: out.pdf.",
    ) as send_mock:
        result = await bridge.send_files([str(doc)], caption="report")

    assert "Sent 1 file" in result
    send_mock.assert_awaited_once_with(
        client,
        [str(doc)],
        user_id=None,
        chat_id=99,
        caption="report",
    )


@pytest.mark.asyncio
async def test_send_chat_files_tool_uses_max_bridge(tmp_path: Path) -> None:
    from core.tools.execution_context import (
        chat_delivery_scope,
        reset_chat_delivery_scope,
    )
    from core.tools.send_chat_files import SendChatFilesTool

    path = tmp_path / "data.csv"
    path.write_text("a,b\n1,2", encoding="utf-8")

    client = MagicMock()
    bridge = MaxDeliveryBridge(client, user_id=5)

    with patch(
        "integrations.max.outbound.send_file_message",
        new_callable=AsyncMock,
    ):
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
    assert "only available in Telegram or MAX" in result