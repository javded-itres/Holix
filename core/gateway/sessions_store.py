"""Persistent API sessions (Hermes /api/sessions)."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cli.core import ProfileManager


def _default_sessions_path() -> Path:
    root = ProfileManager().get_profile_dir("default").parent.parent
    path = root / "data" / "gateway" / "sessions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(slots=True)
class ApiSession:
    id: str
    profile: str
    title: str = ""
    conversation_id: str = ""
    end_reason: str | None = None
    source: str = "api"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    forked_from: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "profile": self.profile,
            "title": self.title,
            "conversation_id": self.conversation_id,
            "end_reason": self.end_reason,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "forked_from": self.forked_from,
        }


class SessionsStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_sessions_path()
        self._sessions: dict[str, ApiSession] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            for item in raw.get("sessions", []):
                session = ApiSession(**item)
                self._sessions[session.id] = session
        except Exception:
            self._sessions = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "sessions": [asdict(s) for s in self._sessions.values()]}
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def create(
        self,
        *,
        profile: str,
        title: str = "",
        source: str = "api",
    ) -> ApiSession:
        sid = f"sess_{uuid.uuid4().hex[:16]}"
        conv = f"api_{profile}_{sid}"
        session = ApiSession(
            id=sid,
            profile=profile,
            title=title or sid,
            conversation_id=conv,
            source=source or "api",
        )
        self._sessions[sid] = session
        self._save()
        return session

    def list(
        self,
        *,
        profile: str | None = None,
        limit: int = 50,
        offset: int = 0,
        source: str | None = None,
        include_children: bool = True,
    ) -> list[ApiSession]:
        items = list(self._sessions.values())
        if profile:
            items = [s for s in items if s.profile == profile]
        if source and source != "all":
            items = [s for s in items if s.source == source]
        if not include_children:
            items = [s for s in items if not s.forked_from]
        items.sort(key=lambda s: s.updated_at, reverse=True)
        return items[offset : offset + limit]

    def get(self, session_id: str) -> ApiSession | None:
        return self._sessions.get(session_id)

    def update(self, session_id: str, **fields: Any) -> ApiSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        for key, value in fields.items():
            if hasattr(session, key) and value is not None:
                setattr(session, key, value)
        session.updated_at = time.time()
        self._save()
        return session

    def delete(self, session_id: str) -> bool:
        removed = self._sessions.pop(session_id, None) is not None
        if removed:
            self._save()
        return removed

    def fork(self, session_id: str, *, title: str = "") -> ApiSession | None:
        parent = self._sessions.get(session_id)
        if parent is None:
            return None
        child = self.create(profile=parent.profile, title=title or f"fork of {parent.title}")
        child.forked_from = parent.id
        child.conversation_id = f"{parent.conversation_id}_fork_{child.id}"
        self._sessions[child.id] = child
        self._save()
        return child