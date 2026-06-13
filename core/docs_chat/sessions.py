"""Per-visitor docs chat session storage (anonymous client_id)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.env_loader import holix_home

_CLIENT_ID_RE = re.compile(r"^[a-f0-9-]{8,64}$", re.I)
_MAX_MESSAGES = 40
_MAX_CONTENT_LEN = 8000


def _sessions_dir() -> Path:
    path = holix_home() / "data" / "docs_chat"
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_client_id(client_id: str) -> str:
    value = (client_id or "").strip().lower()
    if not _CLIENT_ID_RE.fullmatch(value):
        raise ValueError("invalid client_id")
    return value


def _session_path(client_id: str) -> Path:
    safe = validate_client_id(client_id)
    return _sessions_dir() / f"{safe}.json"


def _trim_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trimmed: list[dict[str, Any]] = []
    for msg in messages[-_MAX_MESSAGES:]:
        role = str(msg.get("role", "")).strip()
        content = str(msg.get("content", "")).strip()[:_MAX_CONTENT_LEN]
        if role not in {"user", "assistant"} or not content:
            continue
        entry: dict[str, Any] = {"role": role, "content": content}
        pages = msg.get("pages")
        if role == "assistant" and isinstance(pages, list) and pages:
            entry["pages"] = [
                {"slug": str(p.get("slug", "")), "title": str(p.get("title", ""))}
                for p in pages
                if p.get("slug")
            ][:8]
        trimmed.append(entry)
    return trimmed


def load_session(client_id: str) -> dict[str, Any]:
    path = _session_path(client_id)
    if not path.is_file():
        return {"client_id": validate_client_id(client_id), "messages": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"client_id": validate_client_id(client_id), "messages": []}
    messages = _trim_messages(data.get("messages") or [])
    return {
        "client_id": validate_client_id(client_id),
        "updated_at": data.get("updated_at"),
        "messages": messages,
    }


def save_session(client_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    cid = validate_client_id(client_id)
    payload = {
        "client_id": cid,
        "updated_at": datetime.now(UTC).isoformat(),
        "messages": _trim_messages(messages),
    }
    path = _session_path(cid)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def history_for_llm(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Plain user/assistant turns for the model (no pages metadata)."""
    out: list[dict[str, str]] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if role in {"user", "assistant"} and content:
            out.append({"role": str(role), "content": str(content)})
    return out[-8:]


def append_exchange(
    client_id: str,
    *,
    user_message: str,
    assistant_message: str,
    pages: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    session = load_session(client_id)
    messages = list(session.get("messages") or [])
    messages.append({"role": "user", "content": user_message.strip()})
    assistant_entry: dict[str, Any] = {
        "role": "assistant",
        "content": assistant_message.strip(),
    }
    if pages:
        assistant_entry["pages"] = pages
    messages.append(assistant_entry)
    return save_session(client_id, messages)


def clear_session(client_id: str) -> None:
    path = _session_path(client_id)
    if path.is_file():
        path.unlink()