"""Create cron jobs from natural-language chat without explicit /cron add."""

from __future__ import annotations

from typing import Any

from core.cron.models import CronJob
from core.cron.nl_intent import CronIntent, detect_cron_intent
from core.cron.store import CronStore


def _host_profile(host: Any) -> str:
    return str(getattr(host, "profile", None) or "default")


def _host_session_id(host: Any) -> str | None:
    session_id = getattr(host, "conversation_id", None)
    if session_id:
        return str(session_id)
    session = getattr(host, "_session", None)
    if session is not None:
        cid = getattr(session, "conversation_id", None)
        if cid:
            return str(cid)
    return None


def _host_notify_targets(host: Any) -> dict[str, Any]:
    session = getattr(host, "_session", None)
    if session is None:
        return {}
    out: dict[str, Any] = {}
    chat_id = getattr(session, "chat_id", None)
    if chat_id is not None:
        out["notify_chat_id"] = int(chat_id)
        return out
    user_id = getattr(session, "user_id", None)
    if user_id is not None:
        out["notify_max_user_id"] = int(user_id)
        reply_chat = getattr(session, "reply_chat_id", None)
        if reply_chat is not None:
            out["notify_max_chat_id"] = int(reply_chat)
    return out


def create_cron_from_intent(host: Any, intent: CronIntent) -> CronJob:
    """Persist a cron job using host profile and messenger notification targets."""
    store = CronStore(_host_profile(host))
    return store.add(
        task=intent.task,
        cron_expression=intent.cron_expression,
        name=intent.task[:48],
        session_id=_host_session_id(host),
        **_host_notify_targets(host),
    )


def format_cron_created_message(job: CronJob, *, intent: CronIntent | None = None) -> str:
    """User-facing confirmation after auto-creating a cron job."""
    notify = ""
    if job.notify_chat_id:
        notify = f"\n📬 Уведомления: Telegram chat {job.notify_chat_id}"
    elif job.notify_max_user_id or job.notify_max_chat_id:
        target = job.notify_max_chat_id or job.notify_max_user_id
        notify = f"\n📬 Уведомления: MAX {target}"
    gateway = "\n⏱ Запуск: gateway должен быть запущен (`holix gateway start`)."
    schedule_hint = ""
    if intent and intent.schedule != job.cron_expression:
        schedule_hint = f"\nРасписание: {intent.schedule} → `{job.cron_expression}`"
    else:
        schedule_hint = f"\nCron: `{job.cron_expression}`"
    return (
        f"✅ Запланирована задача **[{job.id}]** {job.name}\n"
        f"{schedule_hint}\n"
        f"Следующий запуск (UTC): {job.next_run_at or '—'}"
        f"{notify}{gateway}\n"
        f"Список: `/cron list` · отключить: `/cron disable {job.id}`"
    )


def try_auto_create_cron(host: Any, message: str) -> CronJob | None:
    """Detect intent and create a cron job; return the job or None."""
    intent = detect_cron_intent(message)
    if intent is None:
        return None
    return create_cron_from_intent(host, intent)