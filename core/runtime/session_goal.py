"""One session objective that stays active across turns.

While a goal is active the agent does not ask clarifying questions. Stop,
a denied confirmation, or an explicit report pauses or blocks it. A finished
turn that is still active continues once, up to ``goal_max_continuations``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_STATUSES = ("active", "paused", "blocked", "complete")


@dataclass
class SessionGoal:
    objective: str
    status: str = "active"
    report: str = ""
    continuations: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _path(profile: str) -> Path | None:
    try:
        from core.profile.names import profile_dir_for_name

        return profile_dir_for_name(profile) / "data" / "session_goals.json"
    except Exception:
        return None


def _load(profile: str) -> dict[str, Any]:
    path = _path(profile)
    if path is None or not path.is_file():
        return {"sessions": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"sessions": {}}
    if not isinstance(payload, dict):
        return {"sessions": {}}
    payload.setdefault("sessions", {})
    return payload


def _save(profile: str, payload: dict[str, Any]) -> None:
    path = _path(profile)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_goal(profile: str, conversation_id: str) -> SessionGoal | None:
    raw = (_load(profile).get("sessions") or {}).get(conversation_id or "default")
    if not isinstance(raw, dict):
        return None
    objective = str(raw.get("objective") or "").strip()
    if not objective:
        return None
    status = str(raw.get("status") or "active")
    if status not in _STATUSES:
        status = "active"
    return SessionGoal(
        objective=objective,
        status=status,
        report=str(raw.get("report") or ""),
        continuations=int(raw.get("continuations") or 0),
    )


def _put(profile: str, conversation_id: str, goal: SessionGoal | None) -> None:
    payload = _load(profile)
    sessions = payload.setdefault("sessions", {})
    key = conversation_id or "default"
    if goal is None:
        sessions.pop(key, None)
    else:
        sessions[key] = goal.as_dict()
    _save(profile, payload)


def start_goal(profile: str, conversation_id: str, objective: str) -> SessionGoal:
    goal = SessionGoal(objective=objective.strip(), status="active")
    _put(profile, conversation_id, goal)
    return goal


def pause_goal(profile: str, conversation_id: str, reason: str = "") -> SessionGoal | None:
    goal = get_goal(profile, conversation_id)
    if goal is None or goal.status not in {"active", "paused"}:
        return goal
    goal.status = "paused"
    if reason:
        goal.report = reason.strip()
    _put(profile, conversation_id, goal)
    return goal


def resume_goal(profile: str, conversation_id: str) -> SessionGoal | None:
    goal = get_goal(profile, conversation_id)
    if goal is None:
        return None
    goal.status = "active"
    _put(profile, conversation_id, goal)
    return goal


def clear_goal(profile: str, conversation_id: str) -> None:
    _put(profile, conversation_id, None)


def report_goal(
    profile: str,
    conversation_id: str,
    status: str,
    reason: str = "",
) -> SessionGoal | None:
    goal = get_goal(profile, conversation_id)
    if goal is None:
        return None
    wanted = status.strip().lower()
    if wanted not in {"complete", "blocked"}:
        wanted = "blocked"
    goal.status = wanted
    goal.report = reason.strip()
    _put(profile, conversation_id, goal)
    return goal


def questions_blocked(profile: str, conversation_id: str) -> bool:
    goal = get_goal(profile, conversation_id)
    return goal is not None and goal.status == "active"


def goal_prompt_block(profile: str | None, conversation_id: str | None) -> str:
    goal = get_goal(profile or "default", conversation_id or "default")
    if goal is None or goal.status != "active":
        return ""
    return (
        "## Session goal\n"
        f"Keep working until this objective is met or genuinely blocked: {goal.objective}\n"
        "Do not call ask_user. Decide safe reversible choices yourself. "
        "When the objective is met, call session_goal with action=report and "
        "status=complete. If you cannot proceed safely, report status=blocked."
    )


def max_continuations() -> int:
    raw = os.environ.get("HOLIX_GOAL_CONTINUATIONS", "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            return 1
    try:
        from config import settings

        return max(0, int(getattr(settings, "goal_max_continuations", 1) or 0))
    except Exception:
        return 1


def continuation_message(profile: str, conversation_id: str) -> str | None:
    """Next internal user text when an active goal still needs another turn."""
    goal = get_goal(profile, conversation_id)
    if goal is None or goal.status != "active":
        return None
    if goal.continuations >= max_continuations():
        report_goal(
            profile,
            conversation_id,
            "blocked",
            "continuation budget exhausted",
        )
        return None
    goal.continuations += 1
    _put(profile, conversation_id, goal)
    return (
        f"Continue the session goal. Do not ask a clarifying question. Objective: {goal.objective}"
    )
