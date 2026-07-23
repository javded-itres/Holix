"""Public deep links for messenger bots (Telegram / MAX)."""

from __future__ import annotations


def normalize_bot_username(username: str | None) -> str | None:
    handle = (username or "").strip().lstrip("@")
    if not handle or any(ch.isspace() for ch in handle):
        return None
    return handle


def telegram_bot_url(username: str | None) -> str | None:
    handle = normalize_bot_username(username)
    if not handle:
        return None
    return f"https://t.me/{handle}"


def max_bot_url(username: str | None) -> str | None:
    handle = normalize_bot_username(username)
    if not handle:
        return None
    return f"https://max.ru/{handle}"
