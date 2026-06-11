"""In-memory agent runs (Hermes /v1/runs API)."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RunStatus(StrEnum):
    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_APPROVAL = "waiting_approval"


@dataclass(slots=True)
class RunRecord:
    run_id: str
    profile: str
    status: RunStatus
    model: str
    input_text: str
    session_id: str | None = None
    instructions: str | None = None
    output: str | None = None
    error: str | None = None
    usage: dict[str, int] | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    events: list[dict[str, Any]] = field(default_factory=list)
    _cancel: asyncio.Event = field(default_factory=asyncio.Event)
    _approval: asyncio.Event = field(default_factory=asyncio.Event)
    approval_payload: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "object": "helix.run",
            "run_id": self.run_id,
            "status": self.status.value,
            "session_id": self.session_id,
            "model": self.model,
            "output": self.output,
            "error": self.error,
            "usage": self.usage,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class RunsStore:
    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._retention_s = 600.0

    def create(
        self,
        *,
        profile: str,
        model: str,
        input_text: str,
        session_id: str | None = None,
        instructions: str | None = None,
    ) -> RunRecord:
        self._gc()
        run_id = f"run_{uuid.uuid4().hex[:20]}"
        record = RunRecord(
            run_id=run_id,
            profile=profile,
            status=RunStatus.STARTED,
            model=model,
            input_text=input_text,
            session_id=session_id,
            instructions=instructions,
        )
        self._runs[run_id] = record
        return record

    def get(self, run_id: str) -> RunRecord | None:
        self._gc()
        return self._runs.get(run_id)

    def append_event(self, run_id: str, event: dict[str, Any]) -> None:
        run = self._runs.get(run_id)
        if run is None:
            return
        run.events.append(event)
        run.updated_at = time.time()

    def update(self, run_id: str, **fields: Any) -> RunRecord | None:
        run = self._runs.get(run_id)
        if run is None:
            return None
        for key, value in fields.items():
            if key == "status" and isinstance(value, str):
                run.status = RunStatus(value)
            elif hasattr(run, key):
                setattr(run, key, value)
        run.updated_at = time.time()
        return run

    def request_cancel(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        if run is None:
            return False
        run._cancel.set()
        if run.status in {RunStatus.STARTED, RunStatus.RUNNING}:
            run.status = RunStatus.CANCELLED
        run.updated_at = time.time()
        return True

    def resolve_approval(self, run_id: str, decision: dict[str, Any]) -> bool:
        run = self._runs.get(run_id)
        if run is None:
            return False
        run.approval_payload = decision
        run._approval.set()
        run.updated_at = time.time()
        return True

    def _gc(self) -> None:
        cutoff = time.time() - self._retention_s
        terminal = {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
        for rid in list(self._runs):
            run = self._runs[rid]
            if run.status in terminal and run.updated_at < cutoff:
                del self._runs[rid]