"""Per-profile persistence for external CLI bindings and tmux sessions."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from core.platform_compat import resolve_holix_home


def external_cli_dir(profile: str) -> Path:
    return (resolve_holix_home() / "profiles" / profile / "external_clis").resolve()


def bindings_path(profile: str) -> Path:
    return external_cli_dir(profile) / "bindings.json"


def sessions_path(profile: str) -> Path:
    return external_cli_dir(profile) / "sessions.json"


@dataclass(slots=True)
class ExternalCliBinding:
    cli_id: str
    enabled: bool = True
    command: str = ""
    model_slot: str = "coder"
    agent_slot: str = "coder"
    default_cwd: str = ""
    extra_env: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            cli_id=str(data["cli_id"]),
            enabled=bool(data.get("enabled", True)),
            command=str(data.get("command") or ""),
            model_slot=str(data.get("model_slot") or "coder"),
            agent_slot=(
                str(data["agent_slot"])
                if "agent_slot" in data
                else str(data.get("agent_slot") or "coder")
            ),
            default_cwd=str(data.get("default_cwd") or ""),
            extra_env=dict(data.get("extra_env") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LaunchedSession:
    session_id: str
    tmux_session: str
    cli_id: str
    profile: str
    cwd: str
    model_slot: str
    model_name: str
    window_index: int = 0
    pane_index: int = 0
    task_preview: str = ""
    created_at: str = ""
    last_output_at: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            session_id=str(data["session_id"]),
            tmux_session=str(data["tmux_session"]),
            cli_id=str(data["cli_id"]),
            profile=str(data["profile"]),
            cwd=str(data.get("cwd") or ""),
            model_slot=str(data.get("model_slot") or "coder"),
            model_name=str(data.get("model_name") or ""),
            window_index=int(data.get("window_index", 0)),
            pane_index=int(data.get("pane_index", 0)),
            task_preview=str(data.get("task_preview") or ""),
            created_at=str(data.get("created_at") or ""),
            last_output_at=str(data.get("last_output_at") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExternalCliStore:
    def __init__(self, profile: str) -> None:
        self.profile = profile
        external_cli_dir(profile).mkdir(parents=True, exist_ok=True)

    def load_bindings(self) -> dict[str, ExternalCliBinding]:
        path = bindings_path(self.profile)
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        items = raw.get("bindings") if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return {}
        out: dict[str, ExternalCliBinding] = {}
        for item in items:
            if not isinstance(item, dict) or "cli_id" not in item:
                continue
            binding = ExternalCliBinding.from_dict(item)
            out[binding.cli_id] = binding
        return out

    def save_bindings(self, bindings: dict[str, ExternalCliBinding]) -> None:
        data = {"bindings": [b.to_dict() for b in bindings.values()]}
        bindings_path(self.profile).write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def get_binding(self, cli_id: str) -> ExternalCliBinding | None:
        return self.load_bindings().get(cli_id.strip().lower())

    def upsert_binding(self, binding: ExternalCliBinding) -> None:
        bindings = self.load_bindings()
        bindings[binding.cli_id] = binding
        self.save_bindings(bindings)

    def load_sessions(self) -> list[LaunchedSession]:
        path = sessions_path(self.profile)
        if not path.is_file():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        items = raw.get("sessions") if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return []
        out: list[LaunchedSession] = []
        for item in items:
            if isinstance(item, dict) and item.get("session_id"):
                out.append(LaunchedSession.from_dict(item))
        return out

    def save_sessions(self, sessions: list[LaunchedSession]) -> None:
        data = {"sessions": [s.to_dict() for s in sessions]}
        sessions_path(self.profile).write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def add_session(self, session: LaunchedSession) -> None:
        sessions = self.load_sessions()
        sessions = [s for s in sessions if s.session_id != session.session_id]
        sessions.append(session)
        self.save_sessions(sessions)

    def remove_session(self, session_id: str) -> None:
        sessions = [s for s in self.load_sessions() if s.session_id != session_id]
        self.save_sessions(sessions)

    def touch_session_output(self, session_id: str) -> None:
        sessions = self.load_sessions()
        now = datetime.now(UTC).isoformat()
        changed = False
        for idx, session in enumerate(sessions):
            if session.session_id == session_id:
                sessions[idx] = LaunchedSession(
                    **{**session.to_dict(), "last_output_at": now}
                )
                changed = True
                break
        if changed:
            self.save_sessions(sessions)