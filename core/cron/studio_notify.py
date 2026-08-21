"""Mirror cron run summaries into Holix Studio persisted chat history."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from core.cron.models import CronJob
from core.cron.session_sync import format_cron_summary
from core.paths import realpath_under, resolve_holix_default_data_dir

logger = logging.getLogger(__name__)

_MAX_MESSAGES = 120
_MAX_TEXT_LEN = 12_000
_CONVERSATION_SAFE_RE = re.compile(r"[^\w.-]+")


def _safe_conversation_id(conversation_id: str) -> str:
    raw = (conversation_id or "studio").strip() or "studio"
    safe = _CONVERSATION_SAFE_RE.sub("_", raw).strip("._")
    return (safe or "studio")[:64]


def _studio_history_path(
    profile: str,
    *,
    workspace_mode: str,
    conversation_id: str,
) -> Path:
    mode = workspace_mode if workspace_mode in {"cwd", "profile"} else "cwd"
    base = resolve_holix_default_data_dir(profile) / "studio" / mode
    base.mkdir(parents=True, exist_ok=True)
    return realpath_under(base, f"{_safe_conversation_id(conversation_id)}.json")


def _write_studio_session(
    profile: str,
    *,
    workspace_mode: str,
    conversation_id: str,
    messages: list[dict],
) -> None:
    allowed = frozenset({"user", "assistant", "system", "tool", "error", "subagent"})
    trimmed: list[dict] = []
    for msg in messages[-_MAX_MESSAGES:]:
        cls = str(msg.get("cls") or msg.get("role") or "").strip()
        body = str(msg.get("text") or msg.get("content") or "").strip()[:_MAX_TEXT_LEN]
        if cls not in allowed or not body:
            continue
        trimmed.append({"cls": cls, "text": body, "ts": msg.get("ts")})
    if not trimmed:
        return
    path = _studio_history_path(
        profile,
        workspace_mode=workspace_mode,
        conversation_id=conversation_id,
    )
    payload = {
        "profile": profile,
        "workspace_mode": workspace_mode,
        "conversation_id": conversation_id,
        "updated_at": datetime.now(UTC).isoformat(),
        "messages": trimmed,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("Failed to write Studio cron session (%s)", path)


def open_studio_cron_session(job: CronJob, response: str) -> str | None:
    """Create a **new** Studio chat session for this cron run (not the open tab)."""
    from core.cron.delivery import new_studio_cron_conversation_id

    summary = format_cron_summary(job, response)
    if not summary.strip():
        return None
    cid = new_studio_cron_conversation_id(job)
    ts = datetime.now(UTC).isoformat()
    task = (job.task or job.name or job.id).strip() or job.id
    messages = [
        {
            "cls": "user",
            "text": f"[Cron · {job.name or job.id}]\n{task}"[:_MAX_TEXT_LEN],
            "ts": ts,
        },
        {"cls": "assistant", "text": summary[:_MAX_TEXT_LEN], "ts": ts},
    ]
    for mode in ("cwd", "profile"):
        _write_studio_session(
            job.profile,
            workspace_mode=mode,
            conversation_id=cid,
            messages=messages,
        )
    return cid


def mirror_cron_to_studio_chat(job: CronJob, response: str) -> str | None:
    """Open a new Studio session for this run. Returns the conversation id."""
    from core.cron.delivery import delivery_channel

    if delivery_channel(job) != "studio":
        return None
    return open_studio_cron_session(job, response)
