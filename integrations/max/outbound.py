"""Outbound file delivery from Holix agent to MAX chat."""

from __future__ import annotations

import asyncio
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from config import settings
from integrations.max.client import MaxClient
from integrations.max.uploads import detect_upload_type, send_file_message

MediaKind = Literal["image", "video", "audio", "file"]

_IMAGE_SUFFIXES = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif", ".tiff"}
)
_VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"})
_AUDIO_SUFFIXES = frozenset({".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac", ".opus"})


@dataclass(slots=True, frozen=True)
class OutboundFile:
    path: Path
    kind: MediaKind
    size_bytes: int
    mime_type: str
    cleanup: Any = None


def classify_outbound_file(path: Path) -> MediaKind:
    """Classify a local file for MAX upload type selection."""
    return detect_upload_type(path)  # type: ignore[return-value]


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

    max_bytes = max(1, int(settings.max_max_file_mb)) * 1024 * 1024
    seen: set[Path] = set()
    files: list[OutboundFile] = []
    errors: list[str] = []

    from core.workspace import display_path_for_user

    for raw in paths:
        label = display_path_for_user(str(raw), input_path=str(raw))
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

        from core.crypto.delivery_files import materialize_file_for_delivery
        from core.crypto.profile_crypto import ProfileCryptoLockedError
        from core.tools.execution_context import get_profile_name

        try:
            send_path, cleanup = materialize_file_for_delivery(path, profile=get_profile_name())
        except ProfileCryptoLockedError as exc:
            errors.append(f"{label}: {exc}")
            continue
        size = send_path.stat().st_size
        if size > max_bytes:
            cleanup()
            errors.append(
                f"{label}: too large ({size // 1024 // 1024} MB, "
                f"limit {settings.max_max_file_mb} MB)"
            )
            continue
        if size <= 0:
            errors.append(f"{label}: empty file")
            cleanup()
            continue

        mime, _ = mimetypes.guess_type(send_path.name)
        files.append(
            OutboundFile(
                path=send_path,
                kind=classify_outbound_file(send_path),
                size_bytes=size,
                mime_type=(mime or "application/octet-stream"),
                cleanup=cleanup,
            )
        )

    return files, errors


def _cleanup_outbound_files(files: list[OutboundFile]) -> None:
    for item in files:
        if item.cleanup:
            try:
                item.cleanup()
            except Exception:
                pass


async def send_outbound_files(
    client: MaxClient,
    paths: list[str | Path],
    *,
    user_id: int | None = None,
    chat_id: int | None = None,
    caption: str = "",
) -> str:
    """Send one or more local files to a MAX chat (one message per file)."""
    files, errors = prepare_outbound_files(paths)
    if not files:
        detail = "; ".join(errors) if errors else "no valid files"
        return f"Error: could not send files — {detail}"

    sent = 0
    cap = (caption or "").strip()
    try:
        for idx, item in enumerate(files):
            item_caption = cap if idx == 0 and cap else ""
            try:
                await send_file_message(
                    client,
                    item.path,
                    user_id=user_id,
                    chat_id=chat_id,
                    caption=item_caption,
                    upload_type=item.kind,
                )
                sent += 1
                await asyncio.sleep(0.08)
            except Exception as exc:
                errors.append(f"{item.path.name}: {exc}")

        if sent == 0:
            detail = "; ".join(errors) if errors else "send failed"
            return f"Error: could not send files — {detail}"

        names = ", ".join(f.path.name for f in files[:sent])
        batch_note = f" ({sent} files)" if sent >= 2 else ""
        err_note = f" Warnings: {'; '.join(errors)}" if errors else ""
        return f"Sent {sent} file(s) to chat{batch_note}: {names}.{err_note}"
    finally:
        _cleanup_outbound_files(files)