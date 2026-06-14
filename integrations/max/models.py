"""Helpers for MAX API update payloads."""

from __future__ import annotations

from typing import Any


def update_type(update: dict[str, Any]) -> str:
    return str(update.get("update_type") or "")


def message_from_update(update: dict[str, Any]) -> dict[str, Any] | None:
    msg = update.get("message")
    return msg if isinstance(msg, dict) else None


def message_has_media(message: dict[str, Any]) -> bool:
    from integrations.max.file_handler import extract_media_attachments

    return bool(extract_media_attachments(message))


def message_text(message: dict[str, Any]) -> str:
    body = message.get("body")
    if not isinstance(body, dict):
        return ""
    text = body.get("text")
    return str(text).strip() if text is not None else ""


def sender_user_id(message: dict[str, Any]) -> int | None:
    sender = message.get("sender")
    if not isinstance(sender, dict):
        return None
    uid = sender.get("user_id")
    if isinstance(uid, int):
        return uid
    if isinstance(uid, str) and uid.isdigit():
        return int(uid)
    return None


def _parse_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def recipient_target(message: dict[str, Any]) -> tuple[int | None, int | None]:
    """Return raw (user_id, chat_id) from message.recipient."""
    recipient = message.get("recipient")
    if not isinstance(recipient, dict):
        return None, None
    return _parse_int(recipient.get("user_id")), _parse_int(recipient.get("chat_id"))


def chat_type_from_message(message: dict[str, Any]) -> str:
    recipient = message.get("recipient")
    if not isinstance(recipient, dict):
        return ""
    return str(recipient.get("chat_type") or "").strip().lower()


def chat_type_from_update(update: dict[str, Any]) -> str:
    kind = update_type(update)
    if kind == "message_created":
        msg = message_from_update(update)
        if msg is not None:
            return chat_type_from_message(msg)
    if kind == "message_callback":
        cb = callback_from_update(update)
        if cb is not None:
            msg = cb.get("message")
            if isinstance(msg, dict):
                return chat_type_from_message(msg)
    if kind == "bot_started":
        return "dialog"
    return ""


def conversation_id_for_max(
    profile: str,
    user_id: int,
    *,
    chat_id: int | None = None,
    chat_type: str | None = None,
) -> str:
    """Stable session id: dialogs use user_id (not ephemeral chat_id)."""
    ct = (chat_type or "").strip().lower()
    if ct == "dialog":
        return f"max_{profile}_{user_id}"
    if chat_id is not None:
        return f"max_{profile}_chat_{chat_id}"
    return f"max_{profile}_{user_id}"


def message_mid_from_message(message: dict[str, Any]) -> str | None:
    """Message id from an incoming update payload (for reply links)."""
    body = message.get("body")
    if isinstance(body, dict):
        mid = _message_id_from_mapping(body)
        if mid:
            return mid
    return _message_id_from_mapping(message)


def reply_kwargs_for_session(
    *,
    user_id: int,
    reply_user_id: int | None = None,
    reply_chat_id: int | None = None,
    chat_type: str | None = None,
) -> dict[str, int]:
    """Return exactly one of user_id or chat_id for POST /messages."""
    _ = chat_type
    if reply_chat_id is not None:
        return {"chat_id": reply_chat_id}
    uid = reply_user_id if reply_user_id is not None else user_id
    return {"user_id": uid}


def reply_target_from_message(message: dict[str, Any]) -> tuple[int | None, int | None]:
    """Return (user_id, chat_id) for POST /messages — exactly one should be set.

    Dialogs and groups: POST /messages?chat_id=… (recipient.chat_id from the update).
    Fallback: user_id when chat_id is absent (e.g. bot_started).
    """
    recipient = message.get("recipient")
    if not isinstance(recipient, dict):
        return sender_user_id(message), None

    chat_id = _parse_int(recipient.get("chat_id"))
    if chat_id is not None:
        return None, chat_id

    sender = sender_user_id(message)
    uid = sender or _parse_int(recipient.get("user_id"))
    return uid, None


def _message_id_from_mapping(data: dict[str, Any]) -> str | None:
    for key in ("mid", "message_id", "id"):
        val = data.get(key)
        if val is not None and str(val).strip():
            return str(val)
    return None


def message_id_from_response(payload: dict[str, Any]) -> str | None:
    if not isinstance(payload, dict):
        return None
    direct = _message_id_from_mapping(payload)
    if direct:
        return direct
    msg = payload.get("message")
    if not isinstance(msg, dict):
        return None
    nested = _message_id_from_mapping(msg)
    if nested:
        return nested
    body = msg.get("body")
    if isinstance(body, dict):
        return _message_id_from_mapping(body)
    return None


def callback_from_update(update: dict[str, Any]) -> dict[str, Any] | None:
    cb = update.get("callback")
    return cb if isinstance(cb, dict) else None


def callback_id_from_update(update: dict[str, Any]) -> str | None:
    cb = callback_from_update(update)
    if cb is None:
        return None
    cid = cb.get("callback_id")
    return str(cid).strip() if cid is not None and str(cid).strip() else None


def callback_payload_from_update(update: dict[str, Any]) -> str:
    cb = callback_from_update(update)
    if cb is None:
        return ""
    payload = cb.get("payload")
    return str(payload).strip() if payload is not None else ""


def callback_reply_target(update: dict[str, Any]) -> tuple[int | None, int | None]:
    cb = callback_from_update(update)
    if cb is None:
        return None, None
    msg = cb.get("message")
    if isinstance(msg, dict):
        return reply_target_from_message(msg)
    uid = user_id_from_update(update)
    return uid, update.get("chat_id") if isinstance(update.get("chat_id"), int) else None


def user_meta_from_update(update: dict[str, Any]) -> dict[str, Any]:
    """Extract user_id, username, first_name, last_name from a MAX update."""
    user: dict[str, Any] | None = None
    kind = update_type(update)
    if kind == "bot_started":
        raw = update.get("user")
        user = raw if isinstance(raw, dict) else None
    elif kind == "message_created":
        msg = message_from_update(update)
        if msg is not None:
            sender = msg.get("sender")
            user = sender if isinstance(sender, dict) else None
    elif kind == "message_callback":
        cb = update.get("callback")
        if isinstance(cb, dict):
            raw = cb.get("user")
            user = raw if isinstance(raw, dict) else None

    if user is None:
        uid = user_id_from_update(update)
        return {"user_id": uid} if uid is not None else {}

    uid = user.get("user_id")
    if isinstance(uid, str) and uid.isdigit():
        uid = int(uid)
    name = str(user.get("name") or "").strip()
    first_name = str(user.get("first_name") or "").strip()
    last_name = str(user.get("last_name") or "").strip()
    if not first_name and name:
        parts = name.split(None, 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""
    username = user.get("username")
    return {
        "user_id": uid if isinstance(uid, int) else None,
        "username": str(username).strip() if username else None,
        "first_name": first_name or None,
        "last_name": last_name or None,
    }


def user_id_from_update(update: dict[str, Any]) -> int | None:
    if update_type(update) == "message_created":
        msg = message_from_update(update)
        if msg is not None:
            return sender_user_id(msg)
    if update_type(update) == "bot_started":
        user = update.get("user")
        if isinstance(user, dict):
            uid = user.get("user_id")
            if isinstance(uid, int):
                return uid
            if isinstance(uid, str) and uid.isdigit():
                return int(uid)
    if update_type(update) == "message_callback":
        callback = update.get("callback")
        if isinstance(callback, dict):
            user = callback.get("user")
            if isinstance(user, dict):
                uid = user.get("user_id")
                if isinstance(uid, int):
                    return uid
    return None