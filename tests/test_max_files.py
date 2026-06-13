"""MAX file attachments and uploads."""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp import web
from integrations.max.file_handler import (
    PendingMaxAttachment,
    attachment_to_pending,
    build_agent_prompt,
    extract_media_attachments,
    format_files_preview_markdown,
    save_max_attachment,
)
from integrations.max.uploads import detect_upload_type, media_attachment

from tests.test_max_client import _start_mock_server


def test_attachment_to_pending_file() -> None:
    att = {
        "type": "file",
        "filename": "notes.txt",
        "size": 120,
        "payload": {"url": "https://cdn.example/notes.txt", "token": "tok"},
    }
    pending = attachment_to_pending(att)
    assert pending is not None
    assert pending.file_name == "notes.txt"
    assert pending.url.endswith("notes.txt")


def test_attachment_to_pending_image() -> None:
    att = {
        "type": "image",
        "payload": {
            "photo_id": 99,
            "url": "https://cdn.example/img.jpg",
            "token": "imgtok",
        },
    }
    pending = attachment_to_pending(att)
    assert pending is not None
    assert pending.attachment_type == "image"
    assert "99" in pending.file_name


def test_extract_media_attachments_skips_keyboard() -> None:
    msg = {
        "body": {
            "text": "hi",
            "attachments": [
                {"type": "inline_keyboard", "payload": {"buttons": []}},
                {
                    "type": "file",
                    "filename": "a.txt",
                    "size": 1,
                    "payload": {"url": "https://ex/a.txt"},
                },
            ],
        }
    }
    items = extract_media_attachments(msg)
    assert len(items) == 1
    assert items[0].file_name == "a.txt"


def test_detect_upload_type() -> None:
    assert detect_upload_type(Path("photo.JPG")) == "image"
    assert detect_upload_type(Path("clip.mp4")) == "video"
    assert detect_upload_type(Path("readme.md")) == "file"


def test_media_attachment_shape() -> None:
    att = media_attachment("file", "abc123")
    assert att == {"type": "file", "payload": {"token": "abc123"}}


def test_format_files_preview_markdown() -> None:
    from integrations.telegram.file_handler import SavedTelegramFile

    files = [
        SavedTelegramFile(
            path=Path("/tmp/x.txt"),
            original_name="x.txt",
            mime_type="text/plain",
            kind="document",
            size_bytes=512,
            description="hello",
        )
    ]
    text = format_files_preview_markdown(files)
    assert "x.txt" in text
    assert "hello" in text


@pytest.mark.asyncio
async def test_save_max_attachment_downloads(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = b"file body"

    async def handler(request: web.Request) -> web.Response:
        return web.Response(body=content)

    runner, base = await _start_mock_server(handler)
    try:
        from integrations.max.client import MaxClient

        item = PendingMaxAttachment("file", f"{base}/dl", "doc.txt", file_size=len(content))
        monkeypatch.setattr(
            "integrations.max.file_handler.profile_files_dir",
            lambda _profile, _sid: tmp_path,
        )
        async with MaxClient("tok", base_url=base) as client:
            saved = await save_max_attachment(client, item, profile="default", storage_id=7)
        assert saved.path.exists()
        assert saved.path.read_bytes() == content
        assert saved.original_name == "doc.txt"
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_request_upload_and_multipart() -> None:
    calls: list[tuple[str, str]] = []

    async def handler(request: web.Request) -> web.Response:
        calls.append((request.method, request.path))
        if request.path == "/uploads":
            host = request.headers.get("Host", "127.0.0.1")
            return web.json_response({"url": f"http://{host}/upload.do?token=up1"})
        if request.path == "/upload.do":
            return web.json_response({"token": "file-token-xyz"})
        return web.json_response({}, status=404)

    runner, base = await _start_mock_server(handler)
    try:
        from integrations.max.client import MaxClient
        from integrations.max.uploads import upload_local_file

        path = Path(__file__)
        async with MaxClient("tok", base_url=base) as client:
            upload_type, token = await upload_local_file(client, path, upload_type="file")
        assert upload_type == "file"
        assert token == "file-token-xyz"
        assert ("POST", "/uploads") in calls
    finally:
        await runner.cleanup()


def test_build_agent_prompt_reuses_telegram_helper() -> None:
    from integrations.telegram.file_handler import SavedTelegramFile

    files = [
        SavedTelegramFile(
            path=Path("/data/x.txt"),
            original_name="x.txt",
            mime_type="text/plain",
            kind="document",
            size_bytes=10,
            description="content",
        )
    ]
    prompt = build_agent_prompt("analyze", files)
    assert "analyze" in prompt
    assert "/data/x.txt" in prompt
    assert "content" in prompt