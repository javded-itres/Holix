"""Outbound file uploads for MAX (POST /uploads)."""

from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path
from typing import Any

from integrations.max.client import MaxApiError, MaxClient

_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".gif", ".tiff", ".bmp", ".heic", ".webp"})
_VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".mkv", ".webm"})
_AUDIO_SUFFIXES = frozenset({".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac"})


def detect_upload_type(path: Path) -> str:
    suffix = path.suffix.lower()
    mime, _ = mimetypes.guess_type(path.name)
    mime = (mime or "").lower()

    if suffix in _IMAGE_SUFFIXES or mime.startswith("image/"):
        return "image"
    if suffix in _VIDEO_SUFFIXES or mime.startswith("video/"):
        return "video"
    if suffix in _AUDIO_SUFFIXES or mime.startswith("audio/"):
        return "audio"
    return "file"


def media_attachment(upload_type: str, token: str) -> dict[str, Any]:
    attach_type = "image" if upload_type == "image" else upload_type
    return {"type": attach_type, "payload": {"token": token}}


async def upload_local_file(
    client: MaxClient,
    path: Path,
    *,
    upload_type: str | None = None,
) -> tuple[str, str]:
    """Upload file to MAX CDN. Returns (upload_type, token)."""
    if not path.is_file():
        raise FileNotFoundError(path)

    upload_type = upload_type or detect_upload_type(path)
    endpoint = await client.request_upload_url(upload_type)
    upload_url = str(endpoint.get("url") or "").strip()
    if not upload_url:
        raise MaxApiError("MAX upload URL is empty")

    pre_token = str(endpoint.get("token") or "").strip()
    result = await client.upload_file_multipart(upload_url, path)
    token = str(result.get("token") or pre_token or "").strip()
    if not token and upload_type == "image":
        token = _token_from_upload_url(upload_url)
    if not token:
        raise MaxApiError("MAX upload did not return token")
    return upload_type, token


def _token_from_upload_url(upload_url: str) -> str:
    from urllib.parse import parse_qs, urlparse

    query = parse_qs(urlparse(upload_url).query)
    for key in ("token", "filetoken", "file_token"):
        values = query.get(key)
        if values and values[0].strip():
            return values[0].strip()
    return ""


async def send_file_message(
    client: MaxClient,
    path: Path,
    *,
    user_id: int | None = None,
    chat_id: int | None = None,
    caption: str = "",
    upload_type: str | None = None,
    retries: int = 4,
) -> dict[str, Any]:
    upload_type, token = await upload_local_file(client, path, upload_type=upload_type)
    attachment = media_attachment(upload_type, token)
    text = caption.strip() or path.name

    delay = 0.4
    last_exc: Exception | None = None
    for attempt in range(retries):
        if attempt:
            await asyncio.sleep(delay)
            delay = min(delay * 1.8, 3.0)
        try:
            from integrations.max.markdown import plain_to_max_html

            body = plain_to_max_html(text) if caption else text
            return await client.send_message(
                body,
                user_id=user_id,
                chat_id=chat_id,
                fmt="html" if caption else None,
                attachments=[attachment],
            )
        except MaxApiError as exc:
            last_exc = exc
            if "attachment.not.ready" not in str(exc).lower() and exc.status != 503:
                raise
    if last_exc:
        raise last_exc
    raise MaxApiError("Failed to send file attachment")