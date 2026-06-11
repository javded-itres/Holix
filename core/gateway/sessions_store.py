"""In-memory API sessions (Hermes /api/sessions)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ApiSession:
    id: str
    profile: str
    title: str = ""
    conversation_id: str = ""
    end_reason: str | None = None
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
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "forked_from": self.forked_from,
        }


class SessionsStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ApiSession] = {}

    def create(self, *, profile: str, title: str = "") -> ApiSession:
        sid = f"sess_{uuid.uuid4().hex[:16]}"
        conv = f"api_{profile}_{sid}"
        session = ApiSession(
            id=sid,
            profile=profile,
            title=title or sid,
            conversation_id=conv,
        )
        self._sessions[sid] = session
        return session

    def list(
        self,
        *,
        profile: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ApiSession]:
        items = list(self._sessions.values())
        if profile:
            items = [s for s in items if s.profile == profile]
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
        return session

    def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    def fork(self, session_id: str, *, title: str = "") -> ApiSession | None:
        parent = self._sessions.get(session_id)
        if parent is None:
            return None
        child = self.create(profile=parent.profile, title=title or f"fork of {parent.title}")
        child.forked_from = parent.id
        child.conversation_id = f"{parent.conversation_id}_fork_{child.id}"
        return child