"""Outbound file delivery from Holix agent to Telegram chat."""

from __future__ import annotations

import asyncio
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from config import settings

MediaKind = Literal["photo", "video", "audio", "document"]

_IMAGE_SUFFIXES = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif", ".tiff"}
)
_VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"})
_AUDIO_SUFFIXES = frozenset({".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac", ".opus"})

# Telegram album rules: photos+videos together; documents/audio only with same type.
_ALBUM_BATCH_KEYS: dict[MediaKind, str] = {
    "photo": "visual",
    "video": "visual",
    "document": "document",
    "audio": "audio",
}

TELEGRAM_ALBUM_MAX = 10


@dataclass(slots=True, frozen=True)
class OutboundFile:
    path: Path
    kind: MediaKind
    size_bytes: int
    mime_type: str


def classify_outbound_file(path: Path) -> MediaKind:
    """Classify a local file for Telegram send method selection."""
    suffix = path.suffix.lower()
    mime, _ = mimetypes.guess_type(path.name)
    mime = (mime or "").lower()

    if suffix in _IMAGE_SUFFIXES or mime.startswith("image/"):
        return "photo"
    if suffix in _VIDEO_SUFFIXES or mime.startswith("video/"):
        return "video"
    if suffix in _AUDIO_SUFFIXES or mime.startswith("audio/"):
        return "audio"
    return "document"


def resolve_outbound_path(raw: str | Path) -> Path:
    from core.workspace import WorkspaceJailError, resolve_tool_path

    try:
        return resolve_tool_path(str(raw))
    except WorkspaceJailError:
        raise
    except Exception:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        else:
            path = path.resolve()
        return path


def prepare_outbound_files(paths: list[str | Path]) -> tuple[list[OutboundFile], list[str]]:
    """Validate paths and return sendable files plus per-path errors."""
    if not paths:
        return [], ["No file paths provided"]

    max_bytes = max(1, int(settings.telegram_max_file_mb)) * 1024 * 1024
    seen: set[Path] = set()
    files: list[OutboundFile] = []
    errors: list[str] = []

    for raw in paths:
        label = str(raw)
        try:
            path = resolve_outbound_path(raw)
        except Exception as exc:
            errors.append(f"{label}: invalid path ({exc})")
            continue

        if path in seen:
            continue
        seen.add(path)

        if not path.exists():
            errors.append(f"{label}: file not found")
            continue
        if not path.is_file():
            errors.append(f"{label}: not a regular file")
            continue

        size = path.stat().st_size
        if size > max_bytes:
            errors.append(
                f"{label}: too large ({size // 1024 // 1024} MB, "
                f"limit {settings.telegram_max_file_mb} MB)"
            )
            continue
        if size <= 0:
            errors.append(f"{label}: empty file")
            continue

        mime, _ = mimetypes.guess_type(path.name)
        files.append(
            OutboundFile(
                path=path,
                kind=classify_outbound_file(path),
                size_bytes=size,
                mime_type=(mime or "application/octet-stream"),
            )
        )

    return files, errors


def _album_batches(files: list[OutboundFile]) -> list[list[OutboundFile]]:
    buckets: dict[str, list[OutboundFile]] = {}
    for item in files:
        key = _ALBUM_BATCH_KEYS[item.kind]
        buckets.setdefault(key, []).append(item)

    batches: list[list[OutboundFile]] = []
    for group in buckets.values():
        for i in range(0, len(group), TELEGRAM_ALBUM_MAX):
            batches.append(group[i : i + TELEGRAM_ALBUM_MAX])
    return batches


def _input_file(path: Path) -> Any:
    from aiogram.types import FSInputFile

    return FSInputFile(path)


async def _send_single(
    bot: Any,
    chat_id: int,
    item: OutboundFile,
    *,
    caption: str = "",
) -> None:
    file = _input_file(item.path)
    cap = caption.strip() or None

    if item.kind == "photo":
        await bot.send_photo(chat_id, file, caption=cap)
        return
    if item.kind == "video":
        await bot.send_video(chat_id, file, caption=cap)
        return
    if item.kind == "audio":
        await bot.send_audio(chat_id, file, caption=cap)
        return
    await bot.send_document(chat_id, file, caption=cap)


async def _send_album(
    bot: Any,
    chat_id: int,
    batch: list[OutboundFile],
    *,
    caption: str = "",
) -> None:
    from aiogram.types import (
        InputMediaAudio,
        InputMediaDocument,
        InputMediaPhoto,
        InputMediaVideo,
    )

    media: list[Any] = []
    cap = caption.strip()
    for idx, item in enumerate(batch):
        file = _input_file(item.path)
        item_caption = cap if idx == 0 and cap else None
        if item.kind == "photo":
            media.append(InputMediaPhoto(media=file, caption=item_caption))
        elif item.kind == "video":
            media.append(InputMediaVideo(media=file, caption=item_caption))
        elif item.kind == "audio":
            media.append(InputMediaAudio(media=file, caption=item_caption))
        else:
            media.append(InputMediaDocument(media=file, caption=item_caption))

    await bot.send_media_group(chat_id, media)


async def send_outbound_files(
    bot: Any,
    chat_id: int,
    paths: list[str | Path],
    *,
    caption: str = "",
) -> str:
    """Send one or more local files to a Telegram chat.

    Uses sendMediaGroup (album) when a batch has 2+ compatible files.
    """
    files, errors = prepare_outbound_files(paths)
    if not files:
        detail = "; ".join(errors) if errors else "no valid files"
        return f"Error: could not send files — {detail}"

    sent = 0
    batches = _album_batches(files)
    for batch_idx, batch in enumerate(batches):
        batch_caption = caption if batch_idx == 0 else ""
        try:
            if len(batch) == 1:
                await _send_single(bot, chat_id, batch[0], caption=batch_caption)
            else:
                await _send_album(bot, chat_id, batch, caption=batch_caption)
            sent += len(batch)
            await asyncio.sleep(0.08)
        except Exception as exc:
            names = ", ".join(f.path.name for f in batch)
            errors.append(f"{names}: {exc}")

    if sent == 0:
        detail = "; ".join(errors) if errors else "send failed"
        return f"Error: could not send files — {detail}"

    names = ", ".join(f.path.name for f in files[:sent])
    album_note = ""
    if sent >= 2:
        album_note = f" (album: {sent} files)"
    err_note = f" Warnings: {'; '.join(errors)}" if errors else ""
    return f"Sent {sent} file(s) to chat{album_note}: {names}.{err_note}"