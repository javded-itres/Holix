"""Persist cron run results into profile conversation memory."""

from __future__ import annotations

from typing import Any

from core.cron.models import CronJob

_SUMMARY_MAX = 2000
_RESULT_MAX = 4000


def format_cron_summary(job: CronJob, response: str) -> str:
    body = (response or "").strip() or "(no response)"
    if len(body) > _SUMMARY_MAX:
        body = body[: _SUMMARY_MAX - 1] + "…"
    return f"[Cron · {job.name or job.id}]\n\n{body}"


async def persist_cron_result(
    agent: Any,
    job: CronJob,
    *,
    response: str,
    run_conversation_id: str,
) -> str:
    """Save assistant output to cron log session and mirror summary to session_id."""
    text = (response or "").strip()
    stored = text[:_RESULT_MAX] if text else None

    if agent and hasattr(agent, "memory") and text:
        meta = {"type": "cron_result", "job_id": job.id, "job_name": job.name}

        try:
            history = await agent.memory.get_conversation(run_conversation_id, limit=5)
            last_assistant = next(
                (m for m in reversed(history) if m.get("role") == "assistant"),
                None,
            )
            if not last_assistant or (last_assistant.get("content") or "").strip() != text:
                await agent.memory.save_message(
                    run_conversation_id,
                    "assistant",
                    text,
                    metadata=meta,
                )
        except Exception:
            pass

        target = (job.session_id or "").strip()
        if target and target != run_conversation_id:
            try:
                await agent.memory.save_message(
                    target,
                    "assistant",
                    format_cron_summary(job, text),
                    metadata={
                        "type": "cron_summary",
                        "job_id": job.id,
                        "cron_run": run_conversation_id,
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
    return conversation_id