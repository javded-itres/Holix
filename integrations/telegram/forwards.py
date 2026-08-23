"""Detect Telegram forwards and label the original author."""

from __future__ import annotations

from typing import Any


def is_telegram_forward(message: Any) -> bool:
    if message is None:
        return False
    return bool(
        getattr(message, "forward_origin", None)
        or getattr(message, "forward_date", None)
        or getattr(message, "forward_from", None)
        or getattr(message, "forward_from_chat", None)
        or getattr(message, "forward_sender_name", None)
    )


def _person_label(user: Any) -> str:
    if user is None:
        return ""
    first = str(getattr(user, "first_name", None) or "").strip()
    last = str(getattr(user, "last_name", None) or "").strip()
    full = " ".join(p for p in (first, last) if p)
    if full:
        return full
    username = str(getattr(user, "username", None) or "").strip()
    if username:
        return f"@{username.lstrip('@')}"
    uid = getattr(user, "id", None)
    return str(uid) if uid not in (None, "") else ""


def _chat_label(chat: Any) -> str:
    if chat is None:
        return ""
    title = str(getattr(chat, "title", None) or "").strip()
    if title:
        return title
    username = str(getattr(chat, "username", None) or "").strip()
    if username:
        return f"@{username.lstrip('@')}"
    return ""


def telegram_forward_origin_label(message: Any) -> str:
    """Human-readable source of a forwarded Telegram message."""
    origin = getattr(message, "forward_origin", None)
    if origin is not None:
        user = getattr(origin, "sender_user", None)
        label = _person_label(user)
        if label:
            return label
        hidden = str(getattr(origin, "sender_user_name", None) or "").strip()
        if hidden:
            return hidden
        chat = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
        chat_label = _chat_label(chat)
        sig = str(getattr(origin, "author_signature", None) or "").strip()
        if chat_label and sig:
            return f"{chat_label} ({sig})"
        if chat_label:
            return chat_label
        if sig:
            return sig
    user = getattr(message, "forward_from", None)
    label = _person_label(user)
    if label:
        return label
    hidden = str(getattr(message, "forward_sender_name", None) or "").strip()
    if hidden:
        return hidden
    return _chat_label(getattr(message, "forward_from_chat", None))


def pending_attachment_from_message(message: Any) -> Any | None:
    """Photo / document / video / animation / video_note → PendingAttachment."""
    from integrations.telegram.media_group import PendingAttachment

    photo = getattr(message, "photo", None)
    if photo:
        item = photo[-1]
        return PendingAttachment(
            file_id=item.file_id,
            file_name=f"photo_{item.file_unique_id}.jpg",
            mime_type="image/jpeg",
            file_size=int(item.file_size or 0),
        )
    doc = getattr(message, "document", None)
    if doc is not None:
        return PendingAttachment(
            file_id=doc.file_id,
            file_name=doc.file_name or f"document_{doc.file_unique_id}",
            mime_type=str(doc.mime_type or ""),
            file_size=int(doc.file_size or 0),
        )
    video = getattr(message, "video", None)
    if video is not None:
        return PendingAttachment(
            file_id=video.file_id,
            file_name=video.file_name or f"video_{video.file_unique_id}.mp4",
            mime_type=str(video.mime_type or "video/mp4"),
            file_size=int(video.file_size or 0),
        )
    animation = getattr(message, "animation", None)
    if animation is not None:
        return PendingAttachment(
            file_id=animation.file_id,
            file_name=animation.file_name or f"animation_{animation.file_unique_id}.mp4",
            mime_type=str(animation.mime_type or "video/mp4"),
            file_size=int(animation.file_size or 0),
        )
    note = getattr(message, "video_note", None)
    if note is not None:
        return PendingAttachment(
            file_id=note.file_id,
            file_name=f"videonote_{note.file_unique_id}.mp4",
            mime_type="video/mp4",
            file_size=int(getattr(note, "file_size", 0) or 0),
        )
    return None


def compose_telegram_forward_prompt(message: Any, *, locale: str, has_media: bool) -> str:
    from integrations.messenger.forwards import combine_forward_text

    raw = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
    return combine_forward_text(
        forwarded=raw,
        origin=telegram_forward_origin_label(message),
        locale=locale,
        has_media=has_media,
    )
