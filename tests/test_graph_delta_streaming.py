"""Delta bridge: bus events must be forwarded live during graph ainvoke."""

from __future__ import annotations

import asyncio

import pytest
from core.agent_events import (
    AgentEventBus,
    AssistantDeltaEvent,
    FinalResponseEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from core.graph.builder import run_graph_loop


class _BusAgent:
    """Minimal agent with a real event bus and react-mode config."""

    def __init__(self, conversation_id: str = "conv-1"):
        self.events = AgentEventBus(name="test")
        self.model = "test-model"
        self.client = None
        self.memory = None
        self.tools = None
        self.skills = None
        self.context_manager = None
        self.config = None
        self._use_langgraph = True
        self._final_response_emitted = False
        self._conversation_id = conversation_id

    def emit(self, event) -> None:
        self.events.emit(event)


def _graph_emitting_to_bus(agent, conv_id: str, deltas: list[str], delay: float):
    """Build a fake compiled graph that emits bus events during ainvoke."""

    class _FakeGraph:
        async def ainvoke(self, state, config):
            for chunk in deltas:
                await asyncio.sleep(delay)
                agent.emit(
                    AssistantDeltaEvent(
                        content=chunk,
                        accumulated=chunk,
                        conversation_id=conv_id,
                    )
                )
            agent.emit(
                ToolCallStartEvent(
                    tool_name="search",
                    tool_id="t1",
                    conversation_id=conv_id,
                )
            )
            agent.emit(
                ToolCallResultEvent(
                    tool_name="search",
                    tool_id="t1",
                    result="ok",
                    conversation_id=conv_id,
                )
            )
            return {
                "final_response": "Готово.",
                "step_count": 1,
                "is_final": True,
            }

    return _FakeGraph()


@pytest.mark.asyncio
async def test_run_graph_loop_forwards_deltas_from_bus() -> None:
    agent = _BusAgent("conv-1")
    fake_graph = _graph_emitting_to_bus(agent, "conv-1", ["Привет", ", ", "мир"], delay=0.01)

    with (
        patch_session(),
        patch_build(fake_graph),
    ):
        events = [
            e
            async for e in run_graph_loop(
                agent,
                "hi",
                "conv-1",
                stream=True,
                execution_mode="react",
            )
        ]

    deltas = [e for e in events if isinstance(e, AssistantDeltaEvent)]
    tool_starts = [e for e in events if isinstance(e, ToolCallStartEvent)]
    tool_results = [e for e in events if isinstance(e, ToolCallResultEvent)]
    finals = [e for e in events if isinstance(e, FinalResponseEvent)]

    assert [d.content for d in deltas] == ["Привет", ", ", "мир"]
    assert len(tool_starts) == 1
    assert len(tool_results) == 1
    assert len(finals) == 1
    assert finals[0].content == "Готово."


@pytest.mark.asyncio
async def test_run_graph_loop_filters_other_conversation_events() -> None:
    agent = _BusAgent("conv-1")
    # Graph emits deltas for a DIFFERENT conversation — must not be forwarded.
    fake_graph = _graph_emitting_to_bus(agent, "conv-2", ["чужая дельта"], delay=0.01)

    with (
        patch_session(),
        patch_build(fake_graph),
    ):
        events = [
            e
            async for e in run_graph_loop(
                agent,
                "hi",
                "conv-1",
                stream=True,
                execution_mode="react",
            )
        ]

    deltas = [e for e in events if isinstance(e, AssistantDeltaEvent)]
    assert deltas == []
    finals = [e for e in events if isinstance(e, FinalResponseEvent)]
    assert len(finals) == 1


@pytest.mark.asyncio
async def test_run_graph_loop_unsubscribes_bus_queue_after_run() -> None:
    agent = _BusAgent("conv-1")
    fake_graph = _graph_emitting_to_bus(agent, "conv-1", ["x"], delay=0.0)

    with (
        patch_session(),
        patch_build(fake_graph),
    ):
        async for _ in run_graph_loop(
            agent,
            "hi",
            "conv-1",
            stream=True,
            execution_mode="react",
        ):
            pass

    assert agent.events.handler_count == 0


@pytest.mark.asyncio
async def test_runner_reemit_does_not_repeat_bus_events() -> None:
    """The graph runner emits yielded events. Bus events must stay single."""
    agent = _BusAgent("conv-1")
    fake_graph = _graph_emitting_to_bus(agent, "conv-1", ["a"], delay=0.0)
    seen: list = []

    with (
        patch_session(),
        patch_build(fake_graph),
    ):
        async for event in run_graph_loop(
            agent,
            "hi",
            "conv-1",
            stream=True,
            execution_mode="react",
        ):
            seen.append(type(event).__name__)
            agent.emit(event)
            if len(seen) > 20:
                break

    assert seen.count("ToolCallStartEvent") == 1
    assert seen.count("ToolCallResultEvent") == 1
    assert seen.count("AssistantDeltaEvent") == 1


def test_agent_emit_drops_an_event_already_on_the_bus() -> None:
    from core.agent import HolixAgent

    bus = AgentEventBus()
    seen: list = []
    bus.subscribe(seen.append)
    agent = object.__new__(HolixAgent)
    agent.events = bus
    agent._event_context = None
    event = ToolCallStartEvent(tool_name="grep", tool_id="t", conversation_id="c")
    HolixAgent.emit(agent, event)
    HolixAgent.emit(agent, seen[0])
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_run_graph_loop_without_bus_still_works() -> None:
    """MagicMock agents (no real bus) run the graph exactly as before."""
    from unittest.mock import AsyncMock, MagicMock, patch

    agent = MagicMock()
    agent.client = MagicMock()
    agent.model = "test-model"
    agent.config = MagicMock()
    agent.config.use_langgraph = False
    agent.config.max_steps = 10
    agent.config.max_steps_per_plan_step = 5
    agent.config.max_refinement_iterations = 2
    agent.config.execution_mode = "react"
    agent._use_langgraph = True
    agent._final_response_emitted = False
    agent.memory = AsyncMock()
    agent.memory.get_conversation = AsyncMock(return_value=[])
    agent.emit = MagicMock()

    final_state = {
        "final_response": "Ответ.",
        "step_count": 1,
        "is_final": True,
    }
    compiled = MagicMock()
    compiled.ainvoke = AsyncMock(return_value=final_state)

    with (
        patch("core.runtime.session.prepare_session", new_callable=AsyncMock) as prep,
        patch("core.graph.builder.create_checkpointer") as cp,
        patch("core.graph.builder.build_holix_graph") as build_graph,
    ):
        prep.return_value = ([{"role": "user", "content": "hi"}], False)
        cp.return_value = None
        build_graph.return_value = compiled

        events = [
            e
            async for e in run_graph_loop(
                agent,
                "hi",
                "tg_pavel_1",
                stream=True,
                execution_mode="react",
            )
        ]

    finals = [e for e in events if isinstance(e, FinalResponseEvent)]
    assert len(finals) == 1
    assert finals[0].content == "Ответ."


def patch_session():
    """Patches prepare_session to return (messages, was_compressed=False)."""
    from unittest.mock import AsyncMock, patch

    return patch(
        "core.runtime.session.prepare_session",
        new_callable=AsyncMock,
        return_value=([{"role": "user", "content": "hi"}], False),
    )


def patch_build(fake_graph):
    from unittest.mock import patch

    return patch("core.graph.builder.build_holix_graph", return_value=fake_graph)
