"""Session todo checklist (whole-list replace), persisted per conversation."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.profile.names import ProfileNameError, profile_dir_for_name

logger = logging.getLogger(__name__)

TODO_STATUSES = ("pending", "in_progress", "completed", "cancelled")
MAX_TODOS = 20
MAX_CONTENT = 240

_STATUS_ALIASES = {
    "pending": "pending",
    "todo": "pending",
    "open": "pending",
    "in_progress": "in_progress",
    "in-progress": "in_progress",
    "inprogress": "in_progress",
    "doing": "in_progress",
    "active": "in_progress",
    "completed": "completed",
    "complete": "completed",
    "done": "completed",
    "finished": "completed",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "skipped": "cancelled",
}

TODO_ICONS = {
    "pending": "☐",
    "in_progress": "▶",
    "completed": "✓",
    "cancelled": "–",
}

_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,47}$")


@dataclass(slots=True)
class TodoItem:
    id: str
    content: str
    status: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _normalize_status(raw: Any) -> str:
    key = str(raw or "pending").strip().lower().replace(" ", "_")
    return _STATUS_ALIASES.get(key, "pending")


def _safe_id(raw: Any, *, fallback: str, used: set[str]) -> str:
    text = str(raw or "").strip()
    if not _ID_RE.fullmatch(text):
        text = fallback
    base = text
    n = 2
    while text in used:
        text = f"{base}-{n}"
        n += 1
    used.add(text)
    return text


def normalize_todo_items(raw: Any) -> list[TodoItem]:
    """Validate a whole-list replace payload. Empty/None → empty list (clear)."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw = raw.get("todos", raw.get("items", raw.get("tasks")))
    if not isinstance(raw, list):
        raise ValueError("todos must be an array of {content, status} objects")
    if len(raw) > MAX_TODOS:
        raise ValueError(f"at most {MAX_TODOS} todos per list")
    used: set[str] = set()
    out: list[TodoItem] = []
    for i, entry in enumerate(raw, start=1):
        if isinstance(entry, str):
            content = entry.strip()
            status = "pending"
            item_id = None
        elif isinstance(entry, dict):
            content = str(entry.get("content") or entry.get("text") or "").strip()
            status = _normalize_status(entry.get("status") or entry.get("state"))
            item_id = entry.get("id")
        else:
            raise ValueError("each todo must be a string or an object")
        if not content:
            raise ValueError("each todo needs non-empty content")
        if len(content) > MAX_CONTENT:
            content = content[: MAX_CONTENT - 1] + "…"
        out.append(
            TodoItem(
                id=_safe_id(item_id, fallback=str(i), used=used),
                content=content,
                status=status,
            )
        )
    return out


def format_todo_lines(items: Iterable[TodoItem | dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in items:
        if isinstance(item, TodoItem):
            status, content = item.status, item.content
        else:
            status = _normalize_status(item.get("status"))
            content = str(item.get("content") or "").strip()
        if not content:
            continue
        icon = TODO_ICONS.get(status, "☐")
        lines.append(f"{icon} {content}")
    return lines


def format_todo_checklist(items: Iterable[TodoItem | dict[str, Any]]) -> str:
    lines = format_todo_lines(items)
    if not lines:
        return ""
    return "Todos\n" + "\n".join(lines)


def format_todo_summary(items: Iterable[TodoItem | dict[str, Any]]) -> str:
    rows = list(items)
    if not rows:
        return "cleared"
    counts = {s: 0 for s in TODO_STATUSES}
    for item in rows:
        status = (
            item.status if isinstance(item, TodoItem) else _normalize_status(item.get("status"))
        )
        counts[status] = counts.get(status, 0) + 1
    bits = [f"{len(rows)} tasks"]
    if counts["in_progress"]:
        bits.append(f"{counts['in_progress']} ▶")
    if counts["pending"]:
        bits.append(f"{counts['pending']} ☐")
    if counts["completed"]:
        bits.append(f"{counts['completed']} ✓")
    return " · ".join(bits)


def format_todo_prompt_block(items: Iterable[TodoItem | dict[str, Any]]) -> str:
    rows = list(items)
    if not rows:
        return ""
    lines = [
        "## Session todos",
        "Current checklist. `todo_write` **replaces** the whole list — send every item.",
        "Statuses: pending, in_progress, completed, cancelled.",
        "This list is a plan, not proof of work.",
    ]
    for item in rows:
        if isinstance(item, TodoItem):
            status, content, item_id = item.status, item.content, item.id
        else:
            status = _normalize_status(item.get("status"))
            content = str(item.get("content") or "").strip()
            item_id = str(item.get("id") or "").strip()
        if not content:
            continue
        prefix = f"{item_id} " if item_id else ""
        lines.append(f"- [{status}] {prefix}{content}")
    return "\n".join(lines)


def items_as_dicts(items: Iterable[TodoItem | dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, TodoItem):
            out.append(item.as_dict())
        else:
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            out.append(
                {
                    "id": str(item.get("id") or "").strip(),
                    "content": content,
                    "status": _normalize_status(item.get("status")),
                }
            )
    return out


class TodoListStore:
    """In-memory lists keyed by profile + conversation, flushed to data/todos.json."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._lists: dict[tuple[str, str], list[TodoItem]] = {}
        self._loaded: set[str] = set()

    def _key(self, profile: str, conversation_id: str) -> tuple[str, str]:
        return (
            (profile or "default").strip() or "default",
            (conversation_id or "default").strip() or "default",
        )

    def _path(self, profile: str) -> Path | None:
        try:
            return profile_dir_for_name(profile) / "data" / "todos.json"
        except ProfileNameError:
            return None

    def _ensure_loaded(self, profile: str) -> None:
        name = (profile or "default").strip() or "default"
        if name in self._loaded:
            return
        self._loaded.add(name)
        path = self._path(name)
        if path is None or not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            logger.debug("todo list load failed for %s", name, exc_info=True)
            return
        sessions = payload.get("sessions") if isinstance(payload, dict) else None
        if not isinstance(sessions, dict):
            return
        for cid, raw in sessions.items():
            try:
                items = normalize_todo_items(raw)
            except ValueError:
                continue
            self._lists[(name, str(cid))] = items

    def _persist(self, profile: str) -> None:
        path = self._path(profile)
        if path is None:
            return
        name = (profile or "default").strip() or "default"
        sessions = {
            cid: [it.as_dict() for it in items]
            for (prof, cid), items in self._lists.items()
            if prof == name
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".todos.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(
                        {"version": 1, "sessions": sessions}, handle, ensure_ascii=False, indent=2
                    )
                    handle.write("\n")
                os.replace(tmp, path)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except OSError:
            logger.debug("todo list persist failed for %s", name, exc_info=True)

    def get(self, profile: str, conversation_id: str) -> list[TodoItem]:
        with self._lock:
            self._ensure_loaded(profile)
            return list(self._lists.get(self._key(profile, conversation_id), []))

    def replace(self, profile: str, conversation_id: str, raw: Any) -> list[TodoItem]:
        items = normalize_todo_items(raw)
        with self._lock:
            self._ensure_loaded(profile)
            key = self._key(profile, conversation_id)
            if items:
                self._lists[key] = items
            else:
                self._lists.pop(key, None)
            self._persist(profile)
        return list(items)

    def clear(self, profile: str, conversation_id: str) -> None:
        self.replace(profile, conversation_id, [])

    def reset(self) -> None:
        with self._lock:
            self._lists.clear()
            self._loaded.clear()


_store = TodoListStore()


def get_todo_store() -> TodoListStore:
    return _store


def get_todos(profile: str, conversation_id: str) -> list[TodoItem]:
    return _store.get(profile, conversation_id)


def replace_todos(profile: str, conversation_id: str, raw: Any) -> list[TodoItem]:
    return _store.replace(profile, conversation_id, raw)


def reset_todo_store() -> None:
    _store.reset()
