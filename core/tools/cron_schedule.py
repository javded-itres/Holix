"""Tool for the agent to register recurring scheduled *agent* tasks."""

from __future__ import annotations

import re
from typing import Any

from core.cron.schedule_parse import parse_schedule_to_cron
from core.cron.store import CronStore
from core.tools.base import BaseTool
from core.tools.execution_context import get_conversation_id, get_profile_name

_LOOKS_LIKE_APP_BUILD = re.compile(
    r"(?:"
    r"создай\s+(?:консольн\w*\s+)?сервис|напиши\s+(?:скрипт|сервис|программ)|"
    r"реализуй|консольн\w*\s+сервис|приложение|daemon|воркер|"
    r"create\s+a\s+(?:service|script|app)|implement\s+a\s+(?:service|script)|"
    r"start_background|background_process"
    r")",
    re.I,
)


def _chat_id_from_bridge() -> int | None:
    from core.tools.execution_context import get_chat_delivery_bridge

    bridge = get_chat_delivery_bridge()
    if bridge is None:
        return None
    cid = getattr(bridge, "_chat_id", None) or getattr(bridge, "chat_id", None)
    if cid is None:
        return None
    try:
        return int(cid)
    except (TypeError, ValueError):
        return None


class ScheduleCronTool(BaseTool):
    """Register a recurring Holix cron job (gateway scheduler runs the agent)."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "schedule_cron"
        self.description = (
            "Schedule Holix to run the *agent* on a recurring timetable (gateway cron). "
            "Use ONLY when the user wants Holix itself to wake up periodically "
            "(e.g. «присылай сводку каждый день в 10», «remind me every Monday»). "
            "Do NOT use for building applications, console services, workers, or scripts "
            "that poll APIs on a timer — implement those as project code "
            "(loop / APScheduler / systemd) and start with start_background_process. "
            "Schedule: natural language or 5-field cron. Gateway must be running."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "schedule": {
                    "type": "string",
                    "description": (
                        "When Holix should run the agent: e.g. 'every day at 10', "
                        "'каждый день в 10 утра', '0 10 * * *', 'every 30 minutes'"
                    ),
                },
                "task": {
                    "type": "string",
                    "description": (
                        "Prompt for the agent on each run (the work to do), "
                        "not instructions to write a new service"
                    ),
                },
                "name": {
                    "type": "string",
                    "description": "Short display name (optional)",
                },
            },
            "required": ["schedule", "task"],
        }

    async def execute(
        self,
        schedule: str,
        task: str,
        name: str = "",
        **_: Any,
    ) -> str:
        task = (task or "").strip()
        if not task:
            return "Error: task is required"
        if _LOOKS_LIKE_APP_BUILD.search(task) or _LOOKS_LIKE_APP_BUILD.search(schedule or ""):
            return (
                "Error: this looks like an application/service to implement, not a Holix cron job. "
                "Write the worker in the project (timer/loop), run it with start_background_process. "
                "Use schedule_cron only when the user wants Holix to run the agent on a schedule "
                "(digests, reminders). Explicit setup: /cron add <schedule> :: <task>."
            )
        try:
            expr = parse_schedule_to_cron((schedule or "").strip())
        except ValueError as exc:
            return f"Error: invalid schedule — {exc}"

        profile = get_profile_name()
        store = CronStore(profile)
        notify_chat_id = _chat_id_from_bridge()
        session_id = get_conversation_id()
        job = store.add(
            task=task,
            cron_expression=expr,
            name=(name or "").strip() or task[:48],
            notify_chat_id=notify_chat_id,
            session_id=session_id if session_id else None,
        )
        lines = [
            f"Cron job created: {job.id}",
            f"Schedule: {schedule.strip()} → {job.cron_expression}",
            f"Next run (UTC): {job.next_run_at or '—'}",
            "Gateway must be running for execution.",
        ]
        if notify_chat_id:
            lines.append(f"Notifications: Telegram chat {notify_chat_id}")
        return "\n".join(lines)


def register_cron_schedule_tool(registry: Any) -> None:
    registry.register(ScheduleCronTool())
