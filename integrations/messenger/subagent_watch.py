"""Live sub-agent watch for Telegram / MAX (one viewer per chat)."""

from __future__ import annotations

import html as html_lib
import secrets
from typing import Any

WATCH_INTERVAL_S = 5.0
WATCH_STEPS = 5
WATCH_LIST_LIMIT = 8

_KIND_ICON = {
    "tool": "🔧",
    "tool_start": "🔧",
    "tool_result": "✓",
    "tool_error": "✗",
    "thinking": "💭",
    "status": "•",
    "error": "⚠",
}


def map_job_tokens(mapping: dict[str, str], job_ids: list[str]) -> dict[str, str]:
    """Replace *mapping* with token→job_id; return job_id→token."""
    mapping.clear()
    out: dict[str, str] = {}
    for jid in job_ids:
        token = secrets.token_hex(4)
        mapping[token] = jid
        out[jid] = token
    return out


def resolve_job_token(mapping: dict[str, str], token: str) -> str:
    return mapping.get(token, token)


def last_activity_steps(
    job: dict[str, Any] | None, *, limit: int = WATCH_STEPS
) -> list[dict[str, Any]]:
    if not job:
        return []
    log = job.get("activity_log") or []
    steps = [e for e in log if isinstance(e, dict)]
    return steps[-max(1, int(limit)) :]


def _step_line(entry: dict[str, Any]) -> str:
    kind = str(entry.get("kind") or "status").strip().lower()
    icon = _KIND_ICON.get(kind, "•")
    msg = " ".join(str(entry.get("message") or "").split())
    tool = str(entry.get("tool_name") or "").strip()
    if tool and tool.lower() not in msg.lower():
        msg = f"{tool}: {msg}" if msg else tool
    n = entry.get("steps_taken")
    prefix = f"{n}. " if n not in (None, "", 0) else ""
    body = msg or kind
    if len(body) > 160:
        body = body[:159] + "…"
    return f"{prefix}{icon} {body}"


def format_watch_text(job: dict[str, Any] | None, *, html: bool, locale: str = "ru") -> str:
    from core.i18n.messages import t

    loc = locale if locale in ("en", "ru") else "ru"
    if not job:
        text = t("tg.subagent_watch.gone", loc)
        return f"<i>{text}</i>" if html else text

    name = str(job.get("name") or job.get("id") or "?").strip()
    status = str(job.get("status") or "?").strip()
    steps = int(job.get("steps_taken") or 0)
    max_steps = int(job.get("max_steps") or 0)
    preview = " ".join(str(job.get("task_preview") or "").split())[:120]
    activity = " ".join(str(job.get("current_activity") or "").split())[:160]
    step_lines = [_step_line(e) for e in last_activity_steps(job)]
    if not step_lines:
        step_lines = [t("tg.subagent_watch.no_steps", loc)]

    step_bit = f"{steps}/{max_steps}" if max_steps else str(steps)
    title = t("tg.subagent_watch.title", loc, name=name, status=status, steps=step_bit)
    if html:
        esc = html_lib.escape
        lines = [f"<b>{esc(title)}</b>"]
        if preview:
            lines.append(esc(preview))
        if activity and activity not in preview:
            lines.append(f"<i>{esc(activity)}</i>")
        lines.append("")
        for line in step_lines:
            lines.append(esc(line))
        return "\n".join(lines)
    lines = [title]
    if preview:
        lines.append(preview)
    if activity and activity not in preview:
        lines.append(activity)
    lines.append("")
    lines.extend(step_lines)
    return "\n".join(lines)


def format_list_text(jobs: list[dict[str, Any]], *, html: bool, locale: str = "ru") -> str:
    from core.i18n.messages import t

    loc = locale if locale in ("en", "ru") else "ru"
    if not jobs:
        text = t("tg.subagent_watch.none", loc)
        return f"<i>{text}</i>" if html else text
    title = t("tg.subagent_watch.pick", loc)
    if html:
        esc = html_lib.escape
        lines = [f"<b>{esc(title)}</b>"]
        for job in jobs:
            name = str(job.get("name") or "?")
            status = str(job.get("status") or "?")
            preview = " ".join(str(job.get("task_preview") or "").split())[:80]
            line = f"• {name} [{status}]"
            if preview:
                line += f" — {preview}"
            lines.append(esc(line))
        return "\n".join(lines)
    lines = [title]
    for job in jobs:
        name = str(job.get("name") or "?")
        status = str(job.get("status") or "?")
        preview = " ".join(str(job.get("task_preview") or "").split())[:80]
        line = f"• {name} [{status}]"
        if preview:
            line += f" — {preview}"
        lines.append(line)
    return "\n".join(lines)


def list_watchable_jobs(profile: str, agent: Any | None = None) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    if agent is not None and hasattr(agent, "subagents"):
        try:
            summary = agent.subagents.get_status_summary()
            for row in summary.get("agents") or []:
                if not isinstance(row, dict):
                    continue
                jid = str(row.get("id") or row.get("name") or "")
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                jobs.append(row)
        except Exception:
            pass
    if not jobs:
        from core.subagents.runtime_registry import list_jobs

        for row in list_jobs(profile, include_done=True, include_activity=False):
            jid = str(row.get("id") or row.get("name") or "")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            jobs.append(row)
    jobs.sort(key=lambda j: (0 if j.get("running") else 1, str(j.get("name") or "")))
    return jobs[:WATCH_LIST_LIMIT]


def load_watch_job(profile: str, job_id: str, agent: Any | None = None) -> dict[str, Any] | None:
    jid = (job_id or "").strip()
    if not jid:
        return None
    if agent is not None and hasattr(agent, "subagents"):
        try:
            handle = agent.subagents.get_handle(jid)
            if handle is not None:
                row = handle.to_status_dict(include_activity=True, include_result=False)
                row["id"] = jid
                row.setdefault("name", handle.name)
                return row
        except Exception:
            pass
    from core.subagents.runtime_registry import get_job

    return get_job(profile, jid, include_activity=True, include_result=False)


async def terminate_watch_job(agent: Any | None, job_id: str, *, profile: str) -> bool:
    if agent is not None and hasattr(agent, "subagents"):
        try:
            return bool(await agent.subagents.terminate(job_id))
        except Exception:
            pass
    from core.subagents.runtime_registry import request_cancel

    return bool(request_cancel(profile, job_id))


def cancel_session_watch(session: Any) -> None:
    task = getattr(session, "subagent_watch_task", None)
    if task is not None:
        try:
            if not task.done():
                task.cancel()
        except Exception:
            pass
    session.subagent_watch_task = None
    session.subagent_watch_job_id = None
