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


def _is_studio_session(session_id: str | None) -> bool:
    raw = (session_id or "").strip()
    return raw == "studio" or raw.startswith("studio_")


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


def _append_studio_message(
    profile: str,
    *,
    workspace_mode: str,
    conversation_id: str,
    text: str,
) -> None:
    path = _studio_history_path(
        profile,
        workspace_mode=workspace_mode,
        conversation_id=conversation_id,
    )
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = {}
    except (OSError, json.JSONDecodeError):
        data = {}

    messages = list(data.get("messages") or [])
    messages.append(
        {
            "cls": "system",
            "text": text[:_MAX_TEXT_LEN],
            "ts": datetime.now(UTC).isoformat(),
        }
    )
    allowed = frozenset({"user", "assistant", "system", "tool", "error", "subagent"})
    trimmed: list[dict] = []
    for msg in messages[-_MAX_MESSAGES:]:
        cls = str(msg.get("cls") or msg.get("role") or "").strip()
        body = str(msg.get("text") or msg.get("content") or "").strip()[:_MAX_TEXT_LEN]
        if cls not in allowed or not body:
            continue
        trimmed.append({"cls": cls, "text": body, "ts": msg.get("ts")})

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
        logger.exception("Failed to mirror cron result to Studio chat (%s)", path)


def mirror_cron_to_studio_chat(job: CronJob, response: str) -> None:
    """Append cron summary to Studio chat history files for active sessions."""
    session_id = (job.session_id or "").strip()
    if not _is_studio_session(session_id):
        return
    summary = format_cron_summary(job, response)
    if not summary.strip():
        return
    for mode in ("cwd", "profile"):
        _append_studio_message(
            job.profile,
            workspace_mode=mode,
            conversation_id=session_id,
            text=summary,
        )