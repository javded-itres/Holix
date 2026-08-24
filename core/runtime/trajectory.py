"""Append-only session trajectory: what the model/tools did this conversation."""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from core.profile.names import ProfileNameError, profile_dir_for_name

logger = logging.getLogger(__name__)

_SKIP_TYPES = frozenset({"assistant_delta"})
_SECRET_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "token",
        "password",
        "secret",
        "authorization",
        "access_token",
        "refresh_token",
    }
)
_SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9._-]+")
_MAX_FIELD = 800
_MAX_LINE = 4000
_DEFAULT_TAIL = 40
_MAX_TAIL = 200


def _safe_conversation_id(conversation_id: str) -> str:
    raw = (conversation_id or "default").strip() or "default"
    cleaned = _SAFE_ID_RE.sub("_", raw)
    return cleaned[:120] or "default"


def _truncate(value: Any, limit: int = _MAX_FIELD) -> Any:
    if isinstance(value, str):
        text = value
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"
    if isinstance(value, dict):
        return {str(k): _truncate(v, limit) for k, v in list(value.items())[:24]}
    if isinstance(value, list):
        return [_truncate(v, limit) for v in value[:24]]
    return value


def _redact_blob(text: str) -> str:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    return json.dumps(_redact(parsed), ensure_ascii=False)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            folded = str(key).strip().lower().replace("-", "_")
            if folded in _SECRET_KEYS:
                out[str(key)] = "***"
            else:
                out[str(key)] = _redact(item)
        return out
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def event_to_record(event: Any) -> dict[str, Any] | None:
    """Compact JSON-serializable row for one agent event (or None to skip)."""
    etype = str(getattr(getattr(event, "type", None), "value", "") or "").strip()
    if not etype or etype in _SKIP_TYPES:
        return None
    raw: dict[str, Any]
    try:
        raw = event.to_dict() if hasattr(event, "to_dict") else {"type": etype}
    except Exception:
        raw = {"type": etype}
    raw = _redact(_truncate(raw))
    if isinstance(raw.get("arguments_raw"), str):
        raw["arguments_raw"] = _redact_blob(raw["arguments_raw"])
    raw["type"] = etype
    raw.setdefault("conversation_id", getattr(event, "conversation_id", "default") or "default")
    raw.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
    return raw


def format_trace_line(record: dict[str, Any]) -> str:
    ts = str(record.get("timestamp") or "")
    clock = ts[11:19] if len(ts) >= 19 else ts
    etype = str(record.get("type") or "event")
    extra = ""
    if etype.startswith("tool_"):
        extra = str(record.get("tool_name") or "")
        if record.get("duration_ms") is not None:
            try:
                extra = f"{extra} ({float(record['duration_ms']):.0f}ms)".strip()
            except (TypeError, ValueError):
                pass
    elif etype == "final_response":
        extra = str(record.get("content") or "")[:80]
    elif etype == "user_message":
        extra = str(record.get("content") or "")[:80]
    elif etype == "thinking":
        extra = str(record.get("message") or "")[:80]
    elif etype == "error":
        extra = str(record.get("error") or record.get("message") or "")[:80]
    elif etype == "todo_list_updated":
        extra = f"{len(record.get('todos') or [])} items"
    elif etype.startswith("background_process"):
        extra = str(record.get("label") or record.get("process_id") or "")
    elif etype.startswith("subagent_"):
        extra = str(record.get("name") or record.get("agent_type") or "")
    bits = [clock, etype]
    if extra:
        bits.append(" ".join(str(extra).split()))
    return " ".join(bits)


def trajectory_path(profile: str, conversation_id: str) -> Path | None:
    try:
        root = profile_dir_for_name(profile) / "data" / "trajectory"
    except ProfileNameError:
        return None
    return root / f"{_safe_conversation_id(conversation_id)}.jsonl"


class TrajectoryLog:
    """Append-only JSONL per conversation."""

    def __init__(self, profile: str) -> None:
        self.profile = (profile or "default").strip() or "default"
        self._lock = threading.Lock()

    def append(self, event: Any) -> None:
        record = event_to_record(event)
        if not record:
            return
        path = trajectory_path(self.profile, str(record.get("conversation_id") or "default"))
        if path is None:
            return
        try:
            line = json.dumps(record, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return
        if len(line) > _MAX_LINE:
            line = line[: _MAX_LINE - 1] + "…"
        with self._lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            except OSError:
                logger.debug("trajectory append failed", exc_info=True)

    def tail(self, conversation_id: str, *, limit: int = _DEFAULT_TAIL) -> list[dict[str, Any]]:
        path = trajectory_path(self.profile, conversation_id)
        if path is None or not path.is_file():
            return []
        n = max(1, min(int(limit or _DEFAULT_TAIL), _MAX_TAIL))
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out: list[dict[str, Any]] = []
        for line in lines[-n:]:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                out.append(row)
        return out

    def search(
        self,
        conversation_id: str,
        query: str,
        *,
        limit: int = _DEFAULT_TAIL,
    ) -> list[dict[str, Any]]:
        needle = (query or "").strip().lower()
        if not needle:
            return self.tail(conversation_id, limit=limit)
        rows = self.tail(conversation_id, limit=_MAX_TAIL)
        hits = [row for row in rows if needle in json.dumps(row, ensure_ascii=False).lower()]
        n = max(1, min(int(limit or _DEFAULT_TAIL), _MAX_TAIL))
        return hits[-n:]


def format_trace_report(rows: list[dict[str, Any]], *, conversation_id: str = "") -> str:
    if not rows:
        cid = (conversation_id or "").strip()
        return f"no trajectory for {cid}" if cid else "no trajectory"
    header = (
        f"trace {conversation_id} · {len(rows)} events"
        if conversation_id
        else f"{len(rows)} events"
    )
    lines = [header] + [format_trace_line(row) for row in rows]
    return "\n".join(lines)


def attach_trajectory_logger(agent: Any) -> None:
    """Subscribe a disk writer on the agent's event bus (idempotent)."""
    if getattr(agent, "_trajectory_attached", False):
        return
    profile = str(getattr(getattr(agent, "config", None), "profile_name", None) or "default")
    log = TrajectoryLog(profile)
    bus = getattr(agent, "events", None)
    if bus is None or not hasattr(bus, "subscribe"):
        return

    def _on_event(event: Any) -> None:
        try:
            log.append(event)
        except Exception:
            logger.debug("trajectory handler failed", exc_info=True)

    bus.subscribe(_on_event)
    agent._trajectory_log = log
    agent._trajectory_attached = True
