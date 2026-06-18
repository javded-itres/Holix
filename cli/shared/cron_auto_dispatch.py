"""Auto-create cron jobs from natural-language messages in chat hosts."""

from __future__ import annotations

from typing import Any

from core.cron.auto_create import (
    format_cron_created_message,
    try_auto_create_cron,
)
from core.cron.nl_intent import detect_cron_intent


async def try_cron_auto_dispatch(host: Any, message: str) -> bool:
    """If *message* is a recurring schedule request, create cron and notify user."""
    text = (message or "").strip()
    if not text or text.startswith("/"):
        return False
    if detect_cron_intent(text) is None:
        return False

    job = try_auto_create_cron(host, text)
    if job is None:
        return False

    intent = detect_cron_intent(text)
    body = format_cron_created_message(job, intent=intent)

    write = getattr(host, "transcript_write", None)
    if callable(write):
        write(body)
        return True

    send_plain = getattr(host, "_send_plain", None)
    if callable(send_plain):
        await send_plain(body)
        return True

    send_text = getattr(host, "_send_text", None)
    if callable(send_text):
        await send_text(body)
        return True

    return True