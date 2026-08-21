"""Persist cron run results into profile conversation memory."""

from __future__ import annotations

from typing import Any

from core.cron.delivery import delivery_channel, resolve_delivery_conversation_id
from core.cron.models import CronJob

_SUMMARY_MAX = 2000
_RESULT_MAX = 4000


def format_cron_summary(job: CronJob, response: str) -> str:
    body = (response or "").strip() or "(no response)"
    if len(body) > _SUMMARY_MAX:
        body = body[: _SUMMARY_MAX - 1] + "…"
    return f"[Cron · {job.name or job.id}]\n\n{body}"


async def _save_assistant(
    agent: Any,
    conversation_id: str,
    text: str,
    *,
    meta: dict,
) -> None:
    if not agent or not hasattr(agent, "memory") or not text or not conversation_id:
        return
    try:
        history = await agent.memory.get_conversation(conversation_id, limit=5)
        last_assistant = next(
            (m for m in reversed(history) if m.get("role") == "assistant"),
            None,
        )
        if last_assistant and (last_assistant.get("content") or "").strip() == text:
            return
        await agent.memory.save_message(conversation_id, "assistant", text, metadata=meta)
    except Exception:
        pass


async def persist_cron_result(
    agent: Any,
    job: CronJob,
    *,
    response: str,
    run_conversation_id: str,
    recent_ids: list[str] | None = None,
) -> str:
    """Save the run log and deliver a summary to the job's channel.

    Telegram / MAX: assistant summary in the **active** messenger session.
    Studio: a **new** Studio chat session.
    TUI / other: summary in ``job.session_id``.
    """
    text = (response or "").strip()
    stored = text[:_RESULT_MAX] if text else None
    summary = format_cron_summary(job, text) if text else ""
    channel = delivery_channel(job)

    if agent and hasattr(agent, "memory") and text:
        meta = {"type": "cron_result", "job_id": job.id, "job_name": job.name}
        await _save_assistant(agent, run_conversation_id, text, meta=meta)

        if channel in {"telegram", "max", "session"}:
            target = resolve_delivery_conversation_id(job, recent_ids=recent_ids)
            if target and target != run_conversation_id:
                await _save_assistant(
                    agent,
                    target,
                    summary,
                    meta={
                        "type": "cron_summary",
                        "job_id": job.id,
                        "cron_run": run_conversation_id,
                        "channel": channel,
                    },
                )

    if text and channel == "studio":
        try:
            from core.cron.studio_notify import open_studio_cron_session

            studio_cid = open_studio_cron_session(job, text)
            if studio_cid:
                await _save_assistant(
                    agent,
                    studio_cid,
                    summary,
                    meta={
                        "type": "cron_summary",
                        "job_id": job.id,
                        "cron_run": run_conversation_id,
                        "channel": "studio",
                    },
                )
        except Exception:
            pass

    return stored or ""


def cron_session_label(conversation_id: str, *, job_name: str | None = None) -> str:
    """Human-friendly label for /sessions lists."""
    if job_name and conversation_id.startswith("cron-"):
        return f"cron: {job_name}"
    if conversation_id.startswith("cron-"):
        return f"cron: {conversation_id.removeprefix('cron-')}"
    if conversation_id.startswith("studio_cron_"):
        return f"cron: {conversation_id.removeprefix('studio_cron_')}"
    return conversation_id
