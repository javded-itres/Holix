"""Assertions over captured agent events for user-case journeys."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.agent_events import (
    AgentEvent,
    ErrorEvent,
    EventType,
    FinalResponseEvent,
    MaxStepsReachedEvent,
    PlanCompletedEvent,
    PlanGeneratedEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from core.security.confirmation_events import ConfirmationRequestEvent


@dataclass
class JourneyResult:
    """Collected outcome of one user-case run."""

    events: list[AgentEvent] = field(default_factory=list)
    final_text: str = ""
    return_value: str = ""

    @property
    def tool_starts(self) -> list[ToolCallStartEvent]:
        return [e for e in self.events if isinstance(e, ToolCallStartEvent)]

    @property
    def tool_results(self) -> list[ToolCallResultEvent]:
        return [e for e in self.events if isinstance(e, ToolCallResultEvent)]

    @property
    def tool_names(self) -> list[str]:
        return [e.tool_name for e in self.tool_starts]

    @property
    def confirmation_requests(self) -> list[ConfirmationRequestEvent]:
        return [e for e in self.events if isinstance(e, ConfirmationRequestEvent)]

    @property
    def errors(self) -> list[ErrorEvent]:
        # ConfirmationRequestEvent reuses EventType.ERROR as base type but is not
        # an ErrorEvent instance — filter by class only.
        return [e for e in self.events if type(e) is ErrorEvent]

    def assert_tools_called(self, *names: str) -> None:
        """Assert tool start events include these names in order (contiguous subsequence)."""
        if not names:
            return
        got = self.tool_names
        if list(names) == got:
            return
        # Allow extra tools only if expected names appear in order.
        it = iter(got)
        for name in names:
            for actual in it:
                if actual == name:
                    break
            else:
                raise AssertionError(f"Expected tool order including {list(names)}, got {got}")

    def assert_tools_exactly(self, *names: str) -> None:
        got = self.tool_names
        if got != list(names):
            raise AssertionError(f"Expected tools exactly {list(names)}, got {got}")

    def assert_final_contains(self, *needles: str) -> None:
        text = self.final_text or self.return_value or ""
        missing = [n for n in needles if n not in text]
        if missing:
            raise AssertionError(f"Final response missing {missing!r}. Got: {text!r}")

    def assert_no_error_events(self) -> None:
        if self.errors:
            msgs = [getattr(e, "error", str(e)) for e in self.errors]
            raise AssertionError(f"Unexpected ErrorEvent(s): {msgs}")

    def assert_confirmation_requested(self, *tool_names: str) -> None:
        got = [e.tool_name for e in self.confirmation_requests]
        if not got:
            raise AssertionError("Expected ConfirmationRequestEvent, got none")
        if tool_names and got != list(tool_names) and not all(n in got for n in tool_names):
            raise AssertionError(f"Expected confirmation for {list(tool_names)}, got {got}")

    def assert_no_confirmation(self) -> None:
        if self.confirmation_requests:
            names = [e.tool_name for e in self.confirmation_requests]
            raise AssertionError(f"Unexpected ConfirmationRequestEvent(s): {names}")

    def events_of(self, cls: type) -> list[AgentEvent]:
        return [e for e in self.events if isinstance(e, cls)]

    def assert_has_event(self, cls: type) -> AgentEvent:
        found = self.events_of(cls)
        if not found:
            types = [type(e).__name__ for e in self.events]
            raise AssertionError(f"Expected {cls.__name__}, events were: {types}")
        return found[0]

    def assert_plan_generated(self, *, min_steps: int = 1) -> PlanGeneratedEvent:
        ev = self.assert_has_event(PlanGeneratedEvent)
        assert isinstance(ev, PlanGeneratedEvent)
        if ev.step_count < min_steps and len(ev.plan_steps) < min_steps:
            raise AssertionError(
                f"PlanGeneratedEvent has fewer than {min_steps} steps "
                f"(step_count={ev.step_count}, len={len(ev.plan_steps)})"
            )
        return ev

    def assert_plan_completed(self) -> PlanCompletedEvent:
        ev = self.assert_has_event(PlanCompletedEvent)
        assert isinstance(ev, PlanCompletedEvent)
        return ev

    def assert_max_steps_reached(self) -> MaxStepsReachedEvent:
        ev = self.assert_has_event(MaxStepsReachedEvent)
        assert isinstance(ev, MaxStepsReachedEvent)
        return ev

    def assert_context_compressed(self) -> AgentEvent:
        from core.agent_events import ContextCompressedEvent

        return self.assert_has_event(ContextCompressedEvent)

    def tool_result_text(self, tool_name: str) -> str:
        for e in self.tool_results:
            if e.tool_name == tool_name:
                return str(e.result or "")
        raise AssertionError(
            f"No ToolCallResultEvent for {tool_name!r}; "
            f"got {[e.tool_name for e in self.tool_results]}"
        )


def collect_final_text(events: list[AgentEvent]) -> str:
    for e in reversed(events):
        if isinstance(e, FinalResponseEvent) and (e.content or "").strip():
            return e.content
        if getattr(e, "type", None) == EventType.FINAL_RESPONSE:
            content = getattr(e, "content", "") or ""
            if content.strip():
                return content
    return ""
