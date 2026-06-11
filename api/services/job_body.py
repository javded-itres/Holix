"""Normalize Hermes / Helix job request bodies for CronStore."""

from __future__ import annotations

from typing import Any

from core.cron.schedule_parse import parse_schedule_to_cron


def normalize_job_fields(
    data: dict[str, Any],
    *,
    require_task: bool = False,
    require_schedule: bool = False,
) -> dict[str, Any]:
    """Map Hermes fields (prompt, schedule) to Helix cron store fields."""
    out = dict(data)

    task = (out.pop("prompt", None) or out.get("task") or "").strip()
    if task:
        out["task"] = task
    elif require_task:
        raise ValueError("task or prompt is required")

    schedule = out.pop("schedule", None)
    cron_expression = (out.get("cron_expression") or "").strip()
    if schedule:
        out["cron_expression"] = parse_schedule_to_cron(str(schedule))
    elif cron_expression:
        out["cron_expression"] = cron_expression
    elif require_schedule:
        raise ValueError("cron_expression or schedule is required")

    delivery = out.pop("delivery_target", None)
    if delivery is not None and out.get("notify_chat_id") is None:
        if isinstance(delivery, int):
            out["notify_chat_id"] = delivery
        elif isinstance(delivery, str) and delivery.isdigit():
            out["notify_chat_id"] = int(delivery)

    provider = out.pop("provider_override", None)
    if provider and not out.get("model_override"):
        out["model_override"] = str(provider).strip() or None

    skills = out.get("skills")
    if skills is not None and not isinstance(skills, list):
        raise ValueError("skills must be a list of skill names")

    return out


def job_to_api_dict(job: Any) -> dict[str, Any]:
    """Serialize CronJob with Hermes-compatible aliases."""
    data = job.model_dump()
    data["prompt"] = job.task
    data["schedule"] = job.cron_expression
    if job.notify_chat_id is not None:
        data["delivery_target"] = job.notify_chat_id
    return data