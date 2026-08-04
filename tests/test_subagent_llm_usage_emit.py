"""Sub-agents must emit LLMCallCompletedEvent for Studio model.calls metering."""

from __future__ import annotations

from types import SimpleNamespace

from core.agent_events import AgentEventBus, LLMCallCompletedEvent, SubAgentStartedEvent
from core.llm.usage import emit_llm_call_usage
from core.subagents.base import SubAgentConfig, SubAgentHandle, SubAgentResult, SubAgentStatus
from core.subagents.manager import SubAgentManager


def test_emit_llm_call_usage_reaches_parent_bus() -> None:
    bus = AgentEventBus(name="parent")
    seen: list = []
    bus.subscribe(lambda e: seen.append(e))

    parent = SimpleNamespace(emit=lambda e: bus.emit(e), events=bus, config=None)
    total = emit_llm_call_usage(
        parent,
        model="kimi-k2",
        step=2,
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        duration_ms=120.0,
        operation_name="subagent.chat",
    )
    assert total == 15
    assert len(seen) == 1
    assert isinstance(seen[0], LLMCallCompletedEvent)
    assert seen[0].model == "kimi-k2"
    assert seen[0].total_tokens == 15


def test_manager_emits_started_and_finished_with_usage_flags() -> None:
    bus = AgentEventBus(name="parent")
    seen: list = []
    bus.subscribe(lambda e: seen.append(e))

    parent = SimpleNamespace(
        emit=lambda e: bus.emit(e),
        events=bus,
        config=SimpleNamespace(
            confirmation_timeout=30,
            profile_name="test",
            subagent_max_concurrent=4,
        ),
    )
    mgr = SubAgentManager(parent)

    handle = SubAgentHandle(
        name="coder-1",
        config=SubAgentConfig(name="coder-1", agent_type="coder", model="smart"),
        status=SubAgentStatus.COMPLETED,
        agent_type="coder",
        task_preview="do work",
    )
    handle.result = SubAgentResult(
        name="coder-1",
        success=True,
        response="done",
        tokens_used=42,
        llm_calls=2,
        usage_accounted=True,
        model="smart",
        steps_taken=2,
    )

    mgr._emit_started(handle)
    mgr._emit_finished_once(handle)

    types = [type(e).__name__ for e in seen]
    assert "SubAgentStartedEvent" in types
    assert "SubAgentFinishedEvent" in types
    finished = next(e for e in seen if type(e).__name__ == "SubAgentFinishedEvent")
    assert finished.tokens_used == 42
    assert finished.llm_calls == 2
    assert finished.usage_accounted is True
    assert finished.model == "smart"
    assert isinstance(seen[0], SubAgentStartedEvent)
