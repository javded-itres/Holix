"""Minimal A2A data model (spec 0.3 / 1.0 compatible subset)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str = "") -> str:
    body = uuid.uuid4().hex
    return f"{prefix}{body}" if prefix else body


class TaskState(StrEnum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    AUTH_REQUIRED = "auth-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class A2APart(BaseModel):
    """Content part (text-first; files/data optional)."""

    kind: str = "text"  # text | file | data
    text: str | None = None
    # file / data payloads (opaque for MVP)
    file: dict[str, Any] | None = None
    data: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    def as_text(self) -> str:
        if self.kind == "text" and self.text is not None:
            return str(self.text)
        if self.data is not None:
            return str(self.data)
        if self.file is not None:
            return f"[file:{self.file.get('name') or self.file.get('uri') or 'attachment'}]"
        return ""


class A2AMessage(BaseModel):
    role: str = "user"  # user | agent
    parts: list[A2APart] = Field(default_factory=list)
    messageId: str = Field(default_factory=lambda: new_id("msg_"))
    contextId: str | None = None
    taskId: str | None = None
    metadata: dict[str, Any] | None = None

    def text_content(self) -> str:
        chunks = [p.as_text() for p in self.parts]
        return "\n".join(c for c in chunks if c).strip()

    @classmethod
    def from_user_text(
        cls,
        text: str,
        *,
        context_id: str | None = None,
        task_id: str | None = None,
    ) -> A2AMessage:
        return cls(
            role="user",
            parts=[A2APart(kind="text", text=text)],
            contextId=context_id,
            taskId=task_id,
        )

    @classmethod
    def from_agent_text(
        cls,
        text: str,
        *,
        context_id: str | None = None,
        task_id: str | None = None,
    ) -> A2AMessage:
        return cls(
            role="agent",
            parts=[A2APart(kind="text", text=text)],
            contextId=context_id,
            taskId=task_id,
        )

    @classmethod
    def parse(cls, raw: Any) -> A2AMessage:
        if isinstance(raw, cls):
            return raw
        if not isinstance(raw, dict):
            raise ValueError("message must be an object")
        parts_raw = raw.get("parts") or []
        parts: list[A2APart] = []
        for p in parts_raw:
            if not isinstance(p, dict):
                continue
            kind = str(p.get("kind") or p.get("type") or "text")
            if kind in {"text", "text/plain"}:
                kind = "text"
            parts.append(
                A2APart(
                    kind=kind,
                    text=p.get("text"),
                    file=p.get("file") if isinstance(p.get("file"), dict) else None,
                    data=p.get("data") if isinstance(p.get("data"), dict) else None,
                    metadata=p.get("metadata") if isinstance(p.get("metadata"), dict) else None,
                )
            )
        if not parts and raw.get("content"):
            parts = [A2APart(kind="text", text=str(raw["content"]))]
        return cls(
            role=str(raw.get("role") or "user"),
            parts=parts,
            messageId=str(raw.get("messageId") or raw.get("message_id") or new_id("msg_")),
            contextId=raw.get("contextId") or raw.get("context_id"),
            taskId=raw.get("taskId") or raw.get("task_id"),
            metadata=raw.get("metadata") if isinstance(raw.get("metadata"), dict) else None,
        )


class A2ATaskStatus(BaseModel):
    state: TaskState = TaskState.SUBMITTED
    message: A2AMessage | None = None
    timestamp: str = Field(default_factory=_now_iso)


class A2AArtifact(BaseModel):
    artifactId: str = Field(default_factory=lambda: new_id("art_"))
    name: str | None = None
    description: str | None = None
    parts: list[A2APart] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class A2ATask(BaseModel):
    id: str = Field(default_factory=lambda: new_id("task_"))
    contextId: str = Field(default_factory=lambda: new_id("ctx_"))
    status: A2ATaskStatus = Field(default_factory=A2ATaskStatus)
    history: list[A2AMessage] = Field(default_factory=list)
    artifacts: list[A2AArtifact] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    # Holix-internal
    profile: str = "default"
    conversation_id: str | None = None

    def to_public_dict(self, *, history_length: int | None = None) -> dict[str, Any]:
        history = list(self.history)
        if history_length is not None:
            if history_length <= 0:
                history = []
            else:
                history = history[-history_length:]
        payload = {
            "id": self.id,
            "contextId": self.contextId,
            "status": {
                "state": str(self.status.state.value if isinstance(self.status.state, TaskState) else self.status.state),
                "timestamp": self.status.timestamp,
            },
            "artifacts": [a.model_dump(exclude_none=True) for a in self.artifacts],
        }
        if self.status.message is not None:
            payload["status"]["message"] = self.status.message.model_dump(exclude_none=True)
        if history:
            payload["history"] = [m.model_dump(exclude_none=True) for m in history]
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload
