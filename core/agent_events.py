"""
Agent Event System for Holix.

Provides structured, real-time events from the agent loop.
This decouples the core agent logic from any specific UI, logging,
or observability implementation (TUI, CLI, API Gateway, metrics, etc.).

Design goals:
- Lightweight dataclasses (easy to serialize, log, test).
- Extensible EventType enum.
- Hybrid delivery: sync callbacks today + clear path to asyncio.Queue fan-out.
- Zero dependencies on Rich / Textual / any UI framework.
- Backward compatible (optional subscribers).

Revives and improves the design previously sketched in the abandoned TUI attempt.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


class EventType(StrEnum):
    """All known event types emitted by the Holix agent."""

    # Conversation lifecycle
    USER_MESSAGE = "user_message"
    THINKING = "thinking"
    ASSISTANT_DELTA = "assistant_delta"
    FINAL_RESPONSE = "final_response"
    MAX_STEPS_REACHED = "max_steps_reached"

    # Tool execution
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_RESULT = "tool_call_result"
    TOOL_CALL_ERROR = "tool_call_error"

    # Self-improvement / skills
    SELF_IMPROVEMENT_STARTED = "self_improvement_started"
    SKILL_CREATED = "skill_created"
    SELF_IMPROVEMENT_ERROR = "self_improvement_error"

    # Generic / infrastructure
    ERROR = "error"
    LLM_CALL_STARTED = "llm_call_started"
    LLM_CALL_COMPLETED = "llm_call_completed"

    # Context management
    CONTEXT_COMPRESSED = "context_compressed"
    CONTEXT_WARNING = "context_warning"

    # Plan management
    PLAN_GENERATED = "plan_generated"
    PLAN_STEP_COMPLETED = "plan_step_completed"
    PLAN_COMPLETED = "plan_completed"


@dataclass
class EventContext:
    """Correlation IDs for a single agent run (set via HolixAgent.begin_run)."""

    conversation_id: str = "default"
    run_id: str = ""
    plan_id: str = ""


@dataclass
class AgentEvent:
    """Base class for all agent events."""

    type: EventType = field(init=False)   # Set by subclasses
    timestamp: datetime = field(default_factory=datetime.now)
    conversation_id: str = "default"
    run_id: str = ""
    plan_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Subclasses should set self.type in their own __post_init__
        if not hasattr(self, 'type') or self.type is None:
            # Fallback for direct use of base class
            object.__setattr__(self, 'type', EventType.ERROR)

    def to_dict(self) -> dict[str, Any]:
        """Simple dict representation (useful for logging / SSE)."""
        return {
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "conversation_id": self.conversation_id,
            "run_id": self.run_id,
            "plan_id": self.plan_id,
            "metadata": self.metadata,
            **self._extra_fields(),
        }

    def _extra_fields(self) -> dict[str, Any]:
        """Override in subclasses to add typed fields."""
        return {}


# ---------------------------------------------------------------------
# Concrete event types (matching and extending the original TUI design)
# ---------------------------------------------------------------------

@dataclass
class UserMessageEvent(AgentEvent):
    """User sent a message."""
    content: str = ""

    def _extra_fields(self) -> dict[str, Any]:
        return {"content": self.content}


@dataclass
class ThinkingEvent(AgentEvent):
    """Agent is thinking / about to call the LLM."""
    message: str = "Holix is thinking..."

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, 'type', EventType.THINKING)

    def _extra_fields(self) -> dict[str, Any]:
        return {"message": self.message}


@dataclass
class AssistantDeltaEvent(AgentEvent):
    """A chunk of assistant response (token-by-token streaming)."""
    content: str = ""
    accumulated: str = ""

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, 'type', EventType.ASSISTANT_DELTA)

    def _extra_fields(self) -> dict[str, Any]:
        return {"content": self.content, "accumulated": self.accumulated}


@dataclass
class FinalResponseEvent(AgentEvent):
    """Final complete response from the agent."""
    content: str = ""
    tool_calls_used: list[dict[str, Any]] = field(default_factory=list)
    steps_taken: int = 0

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, 'type', EventType.FINAL_RESPONSE)

    def _extra_fields(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "tool_calls_used": self.tool_calls_used,
            "steps_taken": self.steps_taken,
        }


@dataclass
class ToolCallStartEvent(AgentEvent):
    """Agent decided to call a tool."""
    tool_name: str = ""
    tool_id: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    arguments_raw: str = ""

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, 'type', EventType.TOOL_CALL_START)

    def _extra_fields(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_id": self.tool_id,
            "arguments": self.arguments,
            "arguments_raw": self.arguments_raw,
        }


@dataclass
class ToolCallResultEvent(AgentEvent):
    """Tool finished successfully."""
    tool_name: str = ""
    tool_id: str = ""
    result: str = ""
    duration_ms: float | None = None
    truncated: bool = False

    def _extra_fields(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_id": self.tool_id,
            "result": self.result[:500] if self.truncated else self.result,
            "duration_ms": self.duration_ms,
            "truncated": self.truncated,
        }


@dataclass
class ToolCallErrorEvent(AgentEvent):
    """Tool execution failed."""
    tool_name: str = ""
    tool_id: str = ""
    error: str = ""

    def _extra_fields(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_id": self.tool_id,
            "error": self.error,
        }


@dataclass
class MaxStepsReachedEvent(AgentEvent):
    """Agent reached the configured max_steps limit."""
    max_steps: int = 15


@dataclass
class ErrorEvent(AgentEvent):
    """Generic error during agent execution."""
    error: str = ""
    error_type: str = "unknown"
    recoverable: bool = True

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, 'type', EventType.ERROR)


@dataclass
class LLMCallStartedEvent(AgentEvent):
    """About to call the LLM (useful for timing / cost tracking)."""
    model: str = ""
    step: int = 0


@dataclass
class LLMCallCompletedEvent(AgentEvent):
    """LLM call finished (before tool execution or final answer)."""
    model: str = ""
    step: int = 0
    duration_ms: float | None = None
    finish_reason: str | None = None


@dataclass
class SelfImprovementStartedEvent(AgentEvent):
    """Agent decided to analyze the session for skill creation."""
    task_description: str = ""


@dataclass
class SkillCreatedEvent(AgentEvent):
    """A new skill was successfully created and saved."""
    skill_name: str = ""
    description: str = ""
    filepath: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class ContextCompressedEvent(AgentEvent):
    """Context was compressed to fit within the model's context window."""
    original_tokens: int = 0
    compressed_tokens: int = 0
    messages_before: int = 0
    messages_after: int = 0
    summary_preview: str = ""

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, 'type', EventType.CONTEXT_COMPRESSED)

    def _extra_fields(self) -> dict[str, Any]:
        return {
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "messages_before": self.messages_before,
            "messages_after": self.messages_after,
            "summary_preview": self.summary_preview,
        }


@dataclass
class ContextWarningEvent(AgentEvent):
    """Warning about context window usage approaching the limit."""
    usage_percent: float = 0.0
    tokens_used: int = 0
    tokens_total: int = 0
    level: str = "warning"  # "warning" (70%) or "critical" (90%)

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, 'type', EventType.CONTEXT_WARNING)

    def _extra_fields(self) -> dict[str, Any]:
        return {
            "usage_percent": self.usage_percent,
            "tokens_used": self.tokens_used,
            "tokens_total": self.tokens_total,
            "level": self.level,
        }


@dataclass
class PlanGeneratedEvent(AgentEvent):
    """Emitted when plan_node generates a plan (before review)."""
    plan_steps: list[dict[str, Any]] = field(default_factory=list)
    step_count: int = 0

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, 'type', EventType.PLAN_GENERATED)

    def _extra_fields(self) -> dict[str, Any]:
        return {"plan_steps": self.plan_steps, "step_count": self.step_count}


@dataclass
class PlanStepCompletedEvent(AgentEvent):
    """Emitted when a plan step finishes executing."""
    step_number: int = 0
    total_steps: int = 0
    step_description: str = ""
    step_response: str = ""

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, 'type', EventType.PLAN_STEP_COMPLETED)

    def _extra_fields(self) -> dict[str, Any]:
        return {
            "step_number": self.step_number,
            "total_steps": self.total_steps,
            "step_description": self.step_description,
        }


@dataclass
class PlanCompletedEvent(AgentEvent):
    """Emitted when all plan steps are done."""
    total_steps: int = 0

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, 'type', EventType.PLAN_COMPLETED)

    def _extra_fields(self) -> dict[str, Any]:
        return {"total_steps": self.total_steps}


# ---------------------------------------------------------------------
# Event delivery (hybrid design: callbacks now + clear path to Queue)
# ---------------------------------------------------------------------

EventHandler = Callable[[AgentEvent], None | Any]


class AgentEventBus:
    """
    Lightweight event bus for agent events.

    Current implementation (Phase 0 start):
    - Synchronous callbacks with isolation (try/except).
    - Automatic handling of async handlers via asyncio.create_task.

    Future evolution (when TUI lands):
    - Support for asyncio.Queue subscribers.
    - Backpressure / buffering options.
    - Wildcard / filtered subscriptions.
    """

    def __init__(self, name: str = "Holix"):
        self.name = name
        self._handlers: list[EventHandler] = []
        self._async_handlers: list[EventHandler] = []  # tracked separately for clarity
        self._queues: list[asyncio.Queue] = []

    def subscribe(self, handler: EventHandler) -> None:
        """Register a handler. Supports both sync and async callables."""
        if inspect.iscoroutinefunction(handler):
            self._async_handlers.append(handler)
        else:
            self._handlers.append(handler)

    def unsubscribe(self, handler: EventHandler) -> None:
        """Remove a previously registered handler."""
        if handler in self._handlers:
            self._handlers.remove(handler)
        if handler in self._async_handlers:
            self._async_handlers.remove(handler)

    def subscribe_queue(self, maxsize: int = 0) -> asyncio.Queue:
        """Register an asyncio.Queue that receives every emitted event (copy)."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._queues.append(queue)
        return queue

    def unsubscribe_queue(self, queue: asyncio.Queue) -> None:
        """Stop delivering events to a queue created via subscribe_queue."""
        if queue in self._queues:
            self._queues.remove(queue)

    def emit(self, event: AgentEvent) -> None:
        """
        Emit an event to all subscribers.

        - Sync handlers are called immediately (with isolation).
        - Async handlers are scheduled via asyncio.create_task (fire-and-forget).
        """
        # Sync handlers
        for handler in list(self._handlers):  # copy to allow unsubscribe during iteration
            try:
                handler(event)
            except Exception as exc:  # never let a bad handler kill the agent
                # In real life we might want a dead-letter or logging here
                print(f"[AgentEventBus] Handler {handler} failed for {event.type}: {exc}")

        # Async handlers (schedule, don't await)
        for handler in list(self._async_handlers):
            try:
                coro = handler(event)
                asyncio.create_task(coro)  # type: ignore[arg-type]
            except Exception as exc:
                print(f"[AgentEventBus] Failed to schedule async handler {handler}: {exc}")

        for queue in list(self._queues):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def clear(self) -> None:
        """Remove all handlers (useful in tests)."""
        self._handlers.clear()
        self._async_handlers.clear()
        self._queues.clear()

    @property
    def handler_count(self) -> int:
        return len(self._handlers) + len(self._async_handlers) + len(self._queues)


# Convenience type alias for anything that can hold an event bus
class HasEventBus(Protocol):
    events: AgentEventBus


# ---------------------------------------------------------------------
# Helper to create common events quickly
# ---------------------------------------------------------------------

def make_event(
    event_type: EventType | str,
    conversation_id: str = "default",
    **kwargs: Any,
) -> AgentEvent:
    """
    Factory helper. Mostly useful in tests or quick prototyping.

    Example:
        event = make_event(EventType.TOOL_CALL_START, tool_name="read_file", ...)
    """
    if isinstance(event_type, str):
        event_type = EventType(event_type)

    # Map to the proper dataclass when possible
    mapping = {
        EventType.ASSISTANT_DELTA: AssistantDeltaEvent,
        EventType.TOOL_CALL_START: ToolCallStartEvent,
        EventType.TOOL_CALL_RESULT: ToolCallResultEvent,
        EventType.TOOL_CALL_ERROR: ToolCallErrorEvent,
        EventType.FINAL_RESPONSE: FinalResponseEvent,
        EventType.ERROR: ErrorEvent,
        EventType.THINKING: ThinkingEvent,
        EventType.SKILL_CREATED: SkillCreatedEvent,
        EventType.CONTEXT_COMPRESSED: ContextCompressedEvent,
        EventType.CONTEXT_WARNING: ContextWarningEvent,
        EventType.PLAN_GENERATED: PlanGeneratedEvent,
        EventType.PLAN_STEP_COMPLETED: PlanStepCompletedEvent,
        EventType.PLAN_COMPLETED: PlanCompletedEvent,
    }

    cls = mapping.get(event_type, AgentEvent)
    # Do not pass 'type' — subclasses set it in __post_init__
    return cls(conversation_id=conversation_id, **kwargs)  # type: ignore[call-arg]


# ---------------------------------------------------------------------
# Compatibility handlers (restore old print behavior for legacy consumers)
# ---------------------------------------------------------------------

def create_compatibility_print_handler() -> EventHandler:
    """
    Returns a handler that prints events in the old style.

    Useful for:
    - legacy cli.py
    - transitional period while modern CLI is being updated to rich event rendering
    - tests that expect console output
    """
    def handler(event: AgentEvent) -> None:
        if isinstance(event, ToolCallStartEvent):
            print(f"\n[Tool Call] {event.tool_name}")
        elif isinstance(event, ToolCallResultEvent):
            text = event.result
            if event.truncated or len(text) > 200:
                text = text[:200] + "..."
            print(f"[Tool Result] {text}")
        elif isinstance(event, SelfImprovementStartedEvent):
            print("\n[Self-Improvement] Analyzing session for skill creation...")
        elif isinstance(event, SkillCreatedEvent):
            print(f"[Self-Improvement] Created new skill: {event.skill_name}")
            print(f"[Self-Improvement] Saved to: {event.filepath}")
        elif isinstance(event, ErrorEvent) and event.error_type == "self_improvement":
            print(f"[Self-Improvement] Error during self-improvement: {event.error}")
        elif isinstance(event, ThinkingEvent):
            msg = event.message
            # Print important messages, and also generic "thinking" so user sees activity
            if any(kw in msg for kw in ["Initializing", "Registered", "Loaded", "ready", "thinking"]):
                print(msg)
        elif isinstance(event, AssistantDeltaEvent):
            # For compatibility mode we just print the delta (will look a bit raw)
            print(event.content, end="", flush=True)
        elif isinstance(event, MaxStepsReachedEvent):
            print(f"Agent reached maximum steps ({event.max_steps}). Task may be too complex.")

    return handler


def create_rich_cli_handler():
    """
    Returns a handler that uses Holix's Rich utilities for beautiful output.

    This is the recommended handler for the modern `holix chat` experience.
    It provides colored tool calls, markdown rendering, spinners (when used
    together with chat.py logic), etc.
    """
    try:
        from cli.utils.rich_console import (
            console,
            print_info,
            print_success,
            print_tool_call,
        )
    except ImportError:
        # Fallback if called outside CLI context
        return create_compatibility_print_handler()

    def handler(event: AgentEvent) -> None:
        if isinstance(event, ToolCallStartEvent):
            print_tool_call(event.tool_name, status="running")
        elif isinstance(event, ToolCallResultEvent):
            print_tool_call(event.tool_name, status="done")
        elif isinstance(event, ToolCallErrorEvent):
            print_tool_call(event.tool_name, status="error")
        elif isinstance(event, SelfImprovementStartedEvent):
            print_info("Analyzing session for new skill creation...")
        elif isinstance(event, SkillCreatedEvent):
            print_success(f"New skill learned: {event.skill_name}")
        elif isinstance(event, ThinkingEvent):
            if "thinking" in event.message.lower():
                console.print(f"[dim]{event.message}[/dim]")
            else:
                print_info(event.message)
        elif isinstance(event, AssistantDeltaEvent):
            # In rich mode we usually let the main chat loop handle deltas
            # via print_assistant_message, so we stay quiet here.
            pass
        elif isinstance(event, FinalResponseEvent):
            # Usually handled by the caller
            pass
        elif isinstance(event, MaxStepsReachedEvent):
            console.print(f"[yellow]Agent reached maximum steps ({event.max_steps}).[/yellow]")

    return handler


# ---------------------------------------------------------------------
# Default monitoring wiring (used by HolixAgent)
# ---------------------------------------------------------------------

def wire_default_monitoring(bus: AgentEventBus) -> None:
    """
    Wire the global StructuredLogger and MetricsCollector as subscribers
    to the given event bus.

    This makes monitoring actually work (previously it was defined but never fed events).
    Called automatically by HolixAgent unless disabled.
    """
    try:
        from core.monitoring.logger import create_logger_subscriber
        from core.monitoring.metrics import create_metrics_subscriber

        bus.subscribe(create_logger_subscriber())
        bus.subscribe(create_metrics_subscriber())
    except Exception as exc:
        # Monitoring must never break agent startup
        print(f"[Holix] Warning: Could not wire default monitoring: {exc}")


__all__ = [
    "EventType",
    "AgentEvent",
    "AgentEventBus",
    # concrete events
    "UserMessageEvent",
    "ThinkingEvent",
    "AssistantDeltaEvent",
    "FinalResponseEvent",
    "ToolCallStartEvent",
    "ToolCallResultEvent",
    "ToolCallErrorEvent",
    "MaxStepsReachedEvent",
    "ErrorEvent",
    "LLMCallStartedEvent",
    "LLMCallCompletedEvent",
    "SelfImprovementStartedEvent",
    "SkillCreatedEvent",
    "ContextCompressedEvent",
    "ContextWarningEvent",
    "PlanGeneratedEvent",
    "PlanStepCompletedEvent",
    "PlanCompletedEvent",
    # helpers
    "make_event",
    "HasEventBus",
    "EventHandler",
]
