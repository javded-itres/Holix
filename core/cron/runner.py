"""Execute a single cron job via the Helix agent."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from cli.core import ProfileManager

from core.cron.expressions import format_next_run_iso
from core.cron.models import CronJob
from core.cron.notifier import format_status_message, send_telegram_notification
from core.cron.session_sync import format_cron_summary, persist_cron_result
from core.cron.store import CronStore, runs_log_path
from core.di import create_agent, resolve_runtime_config

logger = logging.getLogger(__name__)


def _append_run_log(profile: str, line: str) -> None:
    path = runs_log_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {line}\n")


async def _gather_agent_status(agent: Any | None) -> dict:
    """Collect current agent status information."""
    status = {
        "session_name": "unknown",
        "model": "unknown",
        "profile": "default",
        "mode": "unknown",
        "active_tasks": [],
    }

    if not agent:
        return status

    try:
        status["model"] = getattr(agent, "model", "unknown") or "unknown"
    except Exception:
        pass

    try:
        cfg = getattr(agent, "config", None)
        if cfg:
            status["profile"] = getattr(cfg, "profile", "default") or "default"
            status["mode"] = getattr(cfg, "execution_mode", "unknown") or "unknown"
    except Exception:
        pass

    try:
        conv_id = getattr(agent, "conversation_id", None)
        if conv_id:
            status["session_name"] = conv_id
    except Exception:
        pass

    try:
        if hasattr(agent, "context") and agent.context:
            ctx = agent.context
            if hasattr(ctx, "active_tasks"):
                status["active_tasks"] = ctx.active_tasks
            elif hasattr(ctx, "pending_tasks"):
                status["active_tasks"] = ctx.pending_tasks
    except Exception:
        pass

    try:
        if hasattr(agent, "memory") and agent.memory:
            mem = agent.memory
            if hasattr(mem, "get_recent"):
                recent = mem.get_recent(limit=5)
                tasks = [r.get("content", "")[:50] for r in recent if r.get("type") == "task"]
                if tasks:
                    status["active_tasks"] = tasks
    except Exception:
        pass

    return status


async def _run_agent_task(agent: Any, job: CronJob, *, prompt: str) -> str:
    """Run agent in headless cron mode; returns final assistant text."""
    run_conv = job.conversation_id()
    guard = getattr(getattr(agent, "tools", None), "_action_guard", None)

    if guard is not None:
        async with guard.background_auto_approve():
            return await agent.run(
                user_input=prompt,
                conversation_id=run_conv,
                execution_mode="react",
            )
    return await agent.run(
        user_input=prompt,
        conversation_id=run_conv,
        execution_mode="react",
    )


async def run_cron_job(job: CronJob) -> None:
    """Run one cron job; updates store with status and schedules next run."""
    store = CronStore(job.profile)
    current = store.get(job.id)
    if current is None or not current.enabled:
        return
    if current.last_status == "running":
        logger.warning("Cron job %s already running, skip", job.id)
        return

    job = current
    job.last_status = "running"
    job.last_error = None
    store.update(job)
    _append_run_log(job.profile, f"START {job.id} {job.name!r}")

    started = time.monotonic()
    container = None
    response_text = ""
    try:
        config = ProfileManager().load_profile(job.profile)
        runtime = resolve_runtime_config(config)
        agent, container = await create_agent(runtime)
        run_conv = job.conversation_id()

        if job.notify_chat_id and "status" in job.task.lower():
            status = await _gather_agent_status(agent)
            ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
            message = format_status_message(
                session_name=status["session_name"],
                model=status["model"],
                profile=status["profile"],
                mode=status["mode"],
                active_tasks=status["active_tasks"] or None,
                timestamp=ts,
            )
            await send_telegram_notification(
                chat_id=job.notify_chat_id,
                message=message,
            )
            response_text = message
            job.last_result = await persist_cron_result(
                agent, job, response=response_text, run_conversation_id=run_conv
            )
            job.last_status = "success"
            job.last_error = None
        else:
            prompt = (
                f"[Scheduled cron job: {job.name}]\n\n"
                f"{job.task}\n\n"
                "This is an automated background run. Complete the task and summarize results."
            )
            response_text = await _run_agent_task(agent, job, prompt=prompt)
            job.last_result = await persist_cron_result(
                agent, job, response=response_text, run_conversation_id=run_conv
            )
            job.last_status = "success"
            job.last_error = None

            if job.notify_chat_id and response_text.strip():
                preview = format_cron_summary(job, response_text)
                await send_telegram_notification(
                    chat_id=job.notify_chat_id,
                    message=preview.replace("\n", "<br>"),
                )

        if response_text.strip():
            preview = response_text.strip().replace("\n", " ")[:240]
            _append_run_log(job.profile, f"RESULT {job.id}: {preview}")

    except Exception as e:
        logger.exception("Cron job %s failed", job.id)
        job.last_status = "error"
        job.last_error = str(e)[:2000]
        _append_run_log(job.profile, f"ERROR {job.id}: {e}")

        if job.notify_chat_id:
            try:
                error_msg = (
                    f"❌ <b>Cron Job Failed</b>\n\n"
                    f"Job: <code>{job.id}</code>\n"
                    f"Error: <code>{str(e)[:200]}</code>"
                )
                await send_telegram_notification(
                    chat_id=job.notify_chat_id,
                    message=error_msg,
                )
            except Exception:
                pass
    finally:
        if container is not None:
            try:
                await container.close()
            except Exception:
                pass
        job.last_run_at = datetime.now(UTC).isoformat()
        job.last_duration_s = round(time.monotonic() - started, 2)
        job.run_count += 1
        try:
            job.next_run_at = format_next_run_iso(job.cron_expression)
        except ValueError:
            job.next_run_at = None
        store.update(job)
        _append_run_log(
            job.profile,
            f"END {job.id} status={job.last_status} duration={job.last_duration_s}s",
        )