"""Route cron run results to Telegram, MAX, or Studio."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from core.cron.models import CronJob

_TIMESTAMP_SUFFIX = re.compile(r"_\d{9,}$")

Channel = str  # telegram | max | studio | session | none


def delivery_channel(job: CronJob) -> Channel:
    """Which UI should receive this job's result."""
    if job.notify_chat_id:
        return "telegram"
    if job.notify_max_user_id or job.notify_max_chat_id:
        return "max"
    sid = (job.session_id or "").strip()
    if sid == "studio" or sid.startswith("studio_"):
        return "studio"
    if sid:
        return "session"
    return "none"


def telegram_conversation_prefix(job: CronJob) -> str | None:
    if not job.notify_chat_id:
        return None
    return f"tg_{job.profile}_{job.notify_chat_id}"


def chat_family_prefix(conversation_id: str) -> str:
    """Strip ``/<new>`` timestamp suffix: ``tg_p_1_1710000000`` → ``tg_p_1``."""
    return _TIMESTAMP_SUFFIX.sub("", (conversation_id or "").strip())


def max_conversation_prefix(job: CronJob) -> str | None:
    if job.notify_max_chat_id is not None:
        return f"max_{job.profile}_chat_{job.notify_max_chat_id}"
    if job.notify_max_user_id is not None:
        return f"max_{job.profile}_{job.notify_max_user_id}"
    sid = (job.session_id or "").strip()
    if sid.startswith("max_"):
        return chat_family_prefix(sid)
    return None


def pick_active_conversation(
    prefix: str,
    recent_ids: list[str],
    *,
    fallback: str,
) -> str:
    """Newest conversation for this chat: exact prefix or ``prefix_<timestamp>``."""
    for cid in recent_ids:
        if cid == prefix or cid.startswith(prefix + "_"):
            return cid
    return fallback or prefix


def resolve_delivery_conversation_id(
    job: CronJob,
    *,
    recent_ids: list[str] | None = None,
) -> str | None:
    """Conversation that should show the result (not the internal ``cron-<id>`` log)."""
    channel = delivery_channel(job)
    recent = [c for c in (recent_ids or []) if c]
    if channel == "telegram":
        prefix = telegram_conversation_prefix(job)
        if not prefix:
            return (job.session_id or "").strip() or None
        fallback = (job.session_id or "").strip() or prefix
        return pick_active_conversation(prefix, recent, fallback=fallback)
    if channel == "max":
        prefix = max_conversation_prefix(job)
        if not prefix:
            return (job.session_id or "").strip() or None
        fallback = (job.session_id or "").strip() or prefix
        return pick_active_conversation(prefix, recent, fallback=fallback)
    if channel == "studio":
        return None  # created at persist time
    if channel == "session":
        return (job.session_id or "").strip() or None
    return None


def new_studio_cron_conversation_id(job: CronJob, *, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S")
    return f"studio_cron_{job.id}_{stamp}"


def is_internal_cron_conversation(conversation_id: str | None) -> bool:
    return (conversation_id or "").startswith("cron-")


def without_internal_cron_sessions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hide ``cron-<job-id>`` logs from Telegram / MAX session pickers."""
    return [
        row
        for row in rows
        if not is_internal_cron_conversation(str(row.get("conversation_id") or ""))
    ]


def html_escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def telegram_html_body(title: str, body: str) -> str:
    """Telegram HTML: real newlines, no ``<br>`` (the API rejects that tag)."""
    return f"<b>{html_escape(title)}</b>\n\n{html_escape(body)}"
