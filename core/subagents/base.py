"""
SubAgent base types — configuration, results, and handles.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

_ACTIVITY_LOG_MAX = 100
_ACTIVITY_TEXT_MAX = 500
_ACTIVITY_DETAILS_MAX = 400


class ProcessMode(StrEnum):
    """How a sub-agent should be executed."""

    ASYNC = "async"  # In-process asyncio.Task (default, I/O-bound)
    PROCESS = "process"  # Separate OS process (CPU-bound, isolation)
    THREAD = "thread"  # In-process thread (rarely needed)


class MemoryAccess(StrEnum):
    """How a sub-agent accesses the parent's memory."""

    SHARED = "shared"  # Read/write access to parent's LTM
    READONLY = "readonly"  # Read-only access to parent's LTM
    ISOLATED = "isolated"  # Own separate memory stores


class SubAgentStatus(StrEnum):
    """Status of a sub-agent."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    LOOP = "loop"


@dataclass
class SubAgentConfig:
    """Configuration for a sub-agent.

    Defines what the sub-agent can do: which model to use,
    which tools, what system prompt, and how it runs.
    """

    name: str  # Unique name (e.g., "researcher")
    agent_type: str = ""  # Registry type (researcher, coder, …)
    system_prompt: str = ""  # Specialized system prompt
    model: str = ""  # Model override (empty = inherit from parent)
    tools: list[str] = field(default_factory=list)  # Subset of tool names
    max_steps: int = 150  # Max reasoning steps
    mode: str = "react"  # Execution mode
    process_mode: ProcessMode = ProcessMode.ASYNC  # How to run
    timeout: float = 3600.0  # Wait / job budget (seconds, 60 min)
    memory_access: MemoryAccess = MemoryAccess.SHARED  # Memory access level
    temperature: float = 0.7  # LLM temperature
    description: str = ""  # Human-readable description
    tags: list[str] = field(default_factory=list)  # Tags for categorization

    # MCP servers enabled for this sub-agent (by server name). Their tools must also
    # be listed in `tools` (or auto-included by runners) for the names to be usable.
    mcp_servers: list[str] = field(default_factory=list)
    mcp_inherit: bool = True
    # Seed child with parent's completed turns (DSH fork-in-process).
    fork: bool = False
    seed_messages: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if isinstance(self.process_mode, str):
            self.process_mode = ProcessMode(self.process_mode)
        if isinstance(self.memory_access, str):
            self.memory_access = MemoryAccess(self.memory_access)


@dataclass
class SubAgentResult:
    """Result from a completed sub-agent execution.

    Contains the response, metadata about tool usage,
    and performance metrics.
    """

    name: str  # Sub-agent name
    success: bool  # Whether the task completed successfully
    response: str = ""  # The sub-agent's final response
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # Tool calls made
    error: str | None = None  # Error message if failed
    duration_ms: float = 0.0  # Execution time in ms
    memory_used: int = 0  # Approximate memory used (bytes)
    steps_taken: int = 0  # Number of reasoning steps
    tokens_used: int = 0  # Sum of LLM tokens (prompt+completion) for this run
    llm_calls: int = 0  # Number of LLM API calls completed
    # True when each LLM call already emitted LLMCallCompletedEvent (Studio meters per-call).
    usage_accounted: bool = False
    model: str = ""  # Model id used for this run (if known)

    @property
    def status(self) -> SubAgentStatus:
        """Derive status from result data."""
        if self.error:
            err = (self.error or "").lower()
            if "timeout" in err:
                return SubAgentStatus.TIMED_OUT
            if err.startswith("loop:") or "tool calls (loop)" in err:
                return SubAgentStatus.LOOP
            if "cancel" in err:
                return SubAgentStatus.CANCELLED
            return SubAgentStatus.FAILED
        return SubAgentStatus.COMPLETED if self.success else SubAgentStatus.FAILED


@dataclass
class SubAgentHandle:
    """Handle to a running or completed sub-agent.

    Provides methods to check status, get results, and cancel.
    """

    name: str  # Sub-agent name
    config: SubAgentConfig = field(default_factory=SubAgentConfig)
    status: SubAgentStatus = SubAgentStatus.PENDING
    task: Any | None = None  # asyncio.Task or multiprocessing.Process
    result: SubAgentResult | None = None
    started_at: float | None = None  # time.monotonic timestamp
    process_id: int | None = None  # OS PID for process-mode agents
    task_preview: str = ""  # Short task description for UI
    agent_type: str = ""  # Registry type (researcher, coder, …)
    spawn_fallback_reason: str = ""  # Set when OS-process spawn fell back to async
    done_event: Any = field(default=None, repr=False)  # asyncio.Event set on completion
    # Live progress for Studio / status UIs
    steps_taken: int = 0
    max_steps: int = 0
    current_activity: str = ""
    last_tool: str = ""
    activity_log: list[dict[str, Any]] = field(default_factory=list)
    last_activity_at: float | None = None  # time.monotonic of last progress / heartbeat
    awaiting_user: bool = False
    user_resume: Any = field(default=None, repr=False)
    steps_at_user_reply: int = 0

    def begin_wait_for_user(self) -> None:
        """Pause further ReAct steps until ``end_wait_for_user``."""
        import asyncio

        self.awaiting_user = True
        ev = self.user_resume
        if ev is None:
            ev = asyncio.Event()
            self.user_resume = ev
        ev.clear()

    def end_wait_for_user(self) -> None:
        """Resume after the human answered; ignore stale loop traces until a new step."""
        self.awaiting_user = False
        self.steps_at_user_reply = int(self.steps_taken or 0)
        ev = self.user_resume
        if ev is not None:
            ev.set()

    async def wait_while_paused(self) -> None:
        if not self.awaiting_user:
            return
        ev = self.user_resume
        if ev is None:
            return
        await ev.wait()

    @property
    def is_running(self) -> bool:
        return self.status == SubAgentStatus.RUNNING

    @property
    def is_done(self) -> bool:
        return self.status in (
            SubAgentStatus.COMPLETED,
            SubAgentStatus.FAILED,
            SubAgentStatus.CANCELLED,
            SubAgentStatus.TIMED_OUT,
            SubAgentStatus.LOOP,
        )

    @property
    def elapsed_ms(self) -> float:
        """Milliseconds since start, or total duration if done."""
        if self.started_at is None:
            return 0.0
        if self.is_done and self.result:
            return self.result.duration_ms
        return (time.monotonic() - self.started_at) * 1000

    def touch_activity(self) -> None:
        """Mark the sub-agent as live without appending an activity log entry."""
        self.last_activity_at = time.monotonic()

    def is_actively_working(self, *, max_idle_s: float = 90.0) -> bool:
        """True when running and progress/heartbeat was seen within max_idle_s."""
        if not self.is_running:
            return False
        now = time.monotonic()
        last = self.last_activity_at
        if last is None and self.started_at is not None:
            # Just started — treat as active until idle window elapses
            last = self.started_at
        if last is None:
            return False
        return (now - last) <= max(0.0, float(max_idle_s))

    def record_activity(
        self,
        kind: str,
        message: str,
        *,
        tool_name: str = "",
        details: str = "",
        steps_taken: int | None = None,
    ) -> dict[str, Any]:
        """Append a UI-visible activity entry and update live fields."""
        self.touch_activity()
        if steps_taken is not None:
            self.steps_taken = max(0, int(steps_taken))
        text = (message or "").strip()
        if len(text) > _ACTIVITY_TEXT_MAX:
            text = text[: _ACTIVITY_TEXT_MAX - 1] + "…"
        detail_text = (details or "").strip()
        if len(detail_text) > _ACTIVITY_DETAILS_MAX:
            detail_text = detail_text[: _ACTIVITY_DETAILS_MAX - 1] + "…"
        tool = (tool_name or "").strip()
        entry: dict[str, Any] = {
            "ts": time.time(),
            "kind": (kind or "status").strip() or "status",
            "message": text,
            "tool_name": tool,
            "details": detail_text,
            "steps_taken": self.steps_taken,
        }
        if text:
            self.current_activity = text
        if tool:
            self.last_tool = tool
        self.activity_log.append(entry)
        if len(self.activity_log) > _ACTIVITY_LOG_MAX:
            self.activity_log = self.activity_log[-_ACTIVITY_LOG_MAX:]
        return entry

    def to_status_dict(
        self,
        *,
        include_activity: bool = True,
        include_result: bool = True,
    ) -> dict[str, Any]:
        """Serialize handle state for APIs and Studio monitoring."""
        cfg = self.config
        payload: dict[str, Any] = {
            "name": self.name,
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "agent_type": self.agent_type or getattr(cfg, "agent_type", "") or "",
            "task_preview": self.task_preview or "",
            "process_mode": (
                cfg.process_mode.value
                if hasattr(cfg.process_mode, "value")
                else str(cfg.process_mode or "async")
            ),
            "process_id": self.process_id,
            "elapsed_ms": round(float(self.elapsed_ms), 1),
            "steps_taken": int(self.steps_taken or 0),
            "max_steps": int(self.max_steps or getattr(cfg, "max_steps", 0) or 0),
            "current_activity": self.current_activity or "",
            "last_tool": self.last_tool or "",
            "running": self.is_running,
            "done": self.is_done,
            "spawn_fallback_reason": self.spawn_fallback_reason or "",
        }
        if getattr(self, "followed_process", False) is True:
            payload["followed_process"] = True
            payload["studio_process_id"] = str(getattr(self, "studio_process_id", "") or "")
            rid = str(getattr(self, "studio_process_run_id", "") or "")
            if rid:
                payload["studio_process_run_id"] = rid
            sdd = getattr(self, "studio_sdd", None)
            if isinstance(sdd, dict) and sdd:
                payload["sdd"] = sdd
        if include_activity:
            payload["activity_log"] = list(self.activity_log or [])
        if include_result and self.result is not None:
            res = self.result
            response = (res.response or "").strip()
            if len(response) > 4000:
                response = response[:3999] + "…"
            error = (res.error or "").strip()
            if len(error) > 1000:
                error = error[:999] + "…"
            tool_calls = list(res.tool_calls or [])
            if len(tool_calls) > 40:
                tool_calls = tool_calls[-40:]
            payload["result"] = {
                "success": bool(res.success),
                "response": response,
                "error": error,
                "duration_ms": float(res.duration_ms or 0),
                "steps_taken": int(res.steps_taken or 0),
                "tool_calls": tool_calls,
            }
        return payload
