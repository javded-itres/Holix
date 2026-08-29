"""Per-conversation plan_mode flag (read-only tool schemas while on)."""

from __future__ import annotations

import threading
from typing import Any

from core.tools.execution_context import get_conversation_id, get_profile_name

_lock = threading.Lock()
_STATE: dict[tuple[str, str], dict[str, Any]] = {}


def _key() -> tuple[str, str]:
    return (
        (get_profile_name() or "default").strip() or "default",
        (get_conversation_id() or "default").strip() or "default",
    )


def is_plan_mode() -> bool:
    with _lock:
        row = _STATE.get(_key())
    return bool(row and row.get("active"))


def get_plan_state() -> dict[str, Any]:
    with _lock:
        row = dict(_STATE.get(_key()) or {})
    row.setdefault("active", False)
    row.setdefault("plan", "")
    return row


def enter_plan_mode(plan: str = "") -> dict[str, Any]:
    row = {"active": True, "plan": str(plan or "")}
    with _lock:
        _STATE[_key()] = row
    return dict(row)


def exit_plan_mode() -> dict[str, Any]:
    with _lock:
        _STATE.pop(_key(), None)
    return {"active": False, "plan": ""}


def set_plan_text(plan: str) -> None:
    with _lock:
        row = _STATE.setdefault(_key(), {"active": True, "plan": ""})
        row["plan"] = str(plan or "")
