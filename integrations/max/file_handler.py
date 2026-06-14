"""MAX photos and documents: save to profile, extract text, vision."""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import settings
from integrations.max.client import MaxClient
from integrations.telegram.file_handler import (
    SavedTelegramFile,
    _is_image,
    _safe_filename,
    _unique_dest,
    build_agent_prompt,
    enrich_saved_file,
)

MEDIA_ATTACHMENT_TYPES = frozenset({"image", "file", "video", "audio"})


@dataclass(slots=True)
class PendingMaxAttachment:
    attachment_type: str
    url: str
    file_name: str
    mime_type: str = ""
    file_size: int = 0
    video_token: str = ""


def message_attachments(message: dict[str, Any]) -> list[dict[str, Any]]:
    body = message.get("body")
    if not isinstance(body, dict):
        return []
    attachments = body.get("attachments")
    if not isinstance(attachments, list):
        return []
    return [a for a in attachments if isinstance(a, dict)]


def attachment_to_pending(attachment: dict[str, Any]) -> PendingMaxAttachment | None:
    kind = str(attachment.get("type") or "")
    if kind not in MEDIA_ATTACHMENT_TYPES:
        return None

    payload = attachment.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    url = str(payload.get("url") or "").strip()
    token = str(payload.get("token") or "").strip()

    if kind == "file":
        name = str(attachment.get("filename") or "file.bin")
        size = int(attachment.get("size") or 0)
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if not url:
            return None
        return PendingMaxAttachment(kind, url, name, mime_type=mime, file_size=size)

    if kind == "image":
        photo_id = payload.get("photo_id", "img")
        name = f"image_{photo_id}.jpg"
        if not url:
            return None
        return PendingMaxAttachment(kind, url, name, mime_type="image/jpeg")

    if kind == "audio":
        name = f"audio_{token[:12] or 'clip'}.m4a"
        if not url:
            return None
        return PendingMaxAttachment(
            kind, url, name, mime_type="audio/mp4", video_token=token
        )

    if kind == "video":
        name = f"video_{token[:12] or 'clip'}.mp4"
        return PendingMaxAttachment(
            kind,
            url,
            name,
            mime_type="video/mp4",
            file_size=0,
            video_token=token,
        )

    return None


def extract_media_attachments(message: dict[str, Any]) -> list[PendingMaxAttachment]:
    out: list[PendingMaxAttachment] = []
    for att in message_attachments(message):
        pending = attachment_to_pending(att)
        if pending is not None:
            out.append(pending)
    return out


def profile_files_dir(profile: str, storage_id: int) -> Path:
    from cli.core import ProfileManager, init_profile, resolve_profile_storage_paths

    mgr = ProfileManager()
    pdir = mgr.get_profile_dir(profile)
    cfg = resolve_profile_storage_paths(profile, init_profile(profile), profile_dir=pdir)
    dest = Path(cfg.data_dir) / "files" / "max" / str(storage_id)
    dest.mkdir(parents=True, exist_ok=True)
    return dest


async def _resolve_download_url(
    client: MaxClient,
    item: PendingMaxAttachment,
) -> str:
    if item.attachment_type == "video" and item.video_token:
        try:
            video = await client.get_video(item.video_token)
            urls = video.get("urls")
            if isinstance(urls, dict):
                for key in ("download", "default", "url"):
                    candidate = urls.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        return candidate.strip()
        except Exception:
            pass
    if not item.url:
        raise RuntimeError("No download URL for attachment")
    return item.url


async def download_max_attachment(
    client: MaxClient,
    item: PendingMaxAttachment,
    dest: Path,
) -> int:
    url = await _resolve_download_url(client, item)
    return await client.download_url(url, dest)


async def save_max_attachment(
    client: MaxClient,
    item: PendingMaxAttachment,
    *,
    profile: str,
    storage_id: int,
) -> SavedTelegramFile:
    max_bytes = int(settings.max_max_file_mb or 20) * 1024 * 1024
    if item.file_size and item.file_size > max_bytes:
        raise RuntimeError(
            f"Файл слишком большой ({item.file_size // 1024 // 1024} MB). "
            f"Лимит: {settings.max_max_file_mb} MB."
        )

    dest_dir = profile_files_dir(profile, storage_id)
    dest = _unique_dest(dest_dir, item.file_name)
    size = await download_max_attachment(client, item, dest)

    if size > max_bytes:
        dest.unlink(missing_ok=True)
        raise RuntimeError(
            f"Файл слишком большой ({size // 1024 // 1024} MB). "
            f"Лимит: {settings.max_max_file_mb} MB."
        )

    mime = (item.mime_type or mimetypes.guess_type(item.file_name)[0] or "").strip()
    kind = "image" if _is_image(mime, item.file_name) else item.attachment_type
    if kind not in {"image", "document"}:
        kind = "document"
    saved = SavedTelegramFile(
        path=dest,
        original_name=_safe_filename(item.file_name),
        mime_type=mime,
        kind=kind if kind == "image" else "document",
        size_bytes=size,
    )
    return await enrich_saved_file(saved, profile=profile)


def format_files_preview_markdown(
    files: list[SavedTelegramFile],
    *,
    errors: list[str] | None = None,
    max_desc_chars: int = 280,
) -> str:
    if not files:
        return "📎 **Файлы**\n\nНичего не сохранено."

    images = sum(1 for f in files if f.kind == "image")
    docs = len(files) - images
    parts = [f"📎 **Сохранено {len(files)}**"]
    if images:
        parts.append(f"фото: {images}")
    if docs:
        parts.append(f"документов: {docs}")
    lines = [" · ".join(parts), ""]

    for idx, item in enumerate(files, 1):
        label = "Фото" if item.kind == "image" else "Документ"
        lines.append(f"{idx}. **{label}** {item.original_name}")
        lines.append(f"   `{item.path}`")
        lines.append(f"   {item.size_bytes // 1024} KB")
        if item.description:
            short = item.description[:max_desc_chars]
            if len(item.description) > max_desc_chars:
                short += "…"
            lines.append(f"   _{short}_")
        lines.append("")

    if errors:
        lines.append(f"⚠️ {'; '.join(errors)}")

    return "\n".join(lines).strip()


__all__ = [
    "PendingMaxAttachment",
    "attachment_to_pending",
    "build_agent_prompt",
    "extract_media_attachments",
    "format_files_preview_markdown",
    "save_max_attachment",
]