"""Build a factual work-status reply (main agent + tasks + sub-agents)."""

from __future__ import annotations

from typing import Any

from core.config_utils import is_subagents_enabled
from core.direct_dispatch.intent import is_status_request, is_work_activity_request
from core.i18n.locale import LocaleStore, normalize_locale
from core.i18n.messages import t


def should_answer_work_status(text: str) -> bool:
    """True when the user asks what is happening now (not a raw /subagents list)."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    return is_work_activity_request(stripped) or is_status_request(stripped)


def _locale(profile_name: str | None) -> str:
    if profile_name:
        return LocaleStore(profile_name).get()
    return normalize_locale(None)


def _clip(text: str | None, *, limit: int = 240) -> str:
    body = (text or "").strip()
    if len(body) <= limit:
        return body
    return body[: limit - 1].rstrip() + "…"


def _format_subagents(agent: Any, locale: str) -> str:
    mgr = getattr(agent, "subagents", None)
    if mgr is None or not is_subagents_enabled(getattr(agent, "config", None)):
        return t("work_status.subagents_disabled", locale)

    summary = mgr.get_status_summary()
    agents = summary.get("agents") or []
    if not summary.get("total"):
        return t("work_status.subagents_empty", locale)

    lines = [
        t(
            "work_status.subagents_header",
            locale,
            total=summary.get("total", 0),
            running=summary.get("running", 0),
        )
    ]
    for item in agents[:8]:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or "?"
        status = item.get("status") or "?"
        preview = _clip(str(item.get("task_preview") or item.get("agent_type") or ""), limit=80)
        preview_suffix = f" — {preview}" if preview else ""
        line = t(
            "work_status.subagent_line",
            locale,
            name=name,
            status=status,
            preview=preview_suffix,
        )
        lines.append(line)
    return "\n".join(lines)


def build_work_status_reply(
    agent: Any,
    *,
    profile_name: str | None = None,
    last_user_message: str | None = None,
    last_assistant_message: str | None = None,
    recent_user_tasks: list[str] | None = None,
) -> str:
    """Factual status: what the main agent is doing and which tasks are active."""
    locale = _locale(profile_name)
    busy = getattr(agent, "_event_context", None) is not None
    main_line = t("work_status.main_busy", locale) if busy else t("work_status.main_idle", locale)

    tasks: list[str] = []
    for raw in recent_user_tasks or []:
        text = (raw or "").strip()
        if text and not should_answer_work_status(text):
            tasks.append(_clip(text, limit=160))
    if not tasks and last_user_message and not should_answer_work_status(last_user_message):
        tasks.append(_clip(last_user_message, limit=160))

    if tasks:
        task_block = "\n".join(f"- {item}" for item in tasks[:3])
    else:
        task_block = t("work_status.tasks_unknown", locale)

    last_action = _clip(last_assistant_message, limit=280)
    if last_action:
        action_block = last_action
    else:
        action_block = t("work_status.action_unknown", locale)

    parts = [
        t("work_status.title", locale),
        "",
        t("work_status.main_label", locale, state=main_line),
        "",
        t("work_status.tasks_label", locale),
        task_block,
        "",
        t("work_status.last_action_label", locale),
        action_block,
        "",
        _format_subagents(agent, locale),
    ]
    return "\n".join(parts).strip()