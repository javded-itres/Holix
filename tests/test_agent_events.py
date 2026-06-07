"""
Tests for the Agent Event System (core/agent_events.py)

Covers:
- Event dataclasses
- AgentEventBus (sync + async handlers, error isolation)
- Helper functions (make_event)
"""

import pytest
import asyncio
from core.agent_events import (
    AgentEvent,
    AgentEventBus,
    EventType,
    ToolCallStartEvent,
    ToolCallResultEvent,
    FinalResponseEvent,
    ErrorEvent,
    AssistantDeltaEvent,
    ThinkingEvent,
    make_event,
)


class TestAgentEvents:
    def test_event_creation_and_to_dict(self):
        """Basic event creation and serialization."""
        event = ToolCallStartEvent(
            tool_name="read_file",
            tool_id="call_123",
            arguments={"path": "main.py"},
            conversation_id="test_conv",
        )

        assert event.type == EventType.TOOL_CALL_START
        assert event.tool_name == "read_file"
        assert event.conversation_id == "test_conv"

        d = event.to_dict()
        assert d["type"] == "tool_call_start"
        assert d["tool_name"] == "read_file"
        assert "timestamp" in d

    def test_make_event_factory(self):
        """Test the convenience factory."""
        event = make_event(
            EventType.ASSISTANT_DELTA,
            conversation_id="conv_1",
            content="Hello",
            accumulated="Hello world",
        )

        assert isinstance(event, AssistantDeltaEvent)
        assert event.content == "Hello"
        assert event.conversation_id == "conv_1"


class TestAgentEventBus:
    def test_sync_handler_receives_event(self):
        """Basic sync subscription and emission."""
        bus = AgentEventBus()
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe(handler)

        event = FinalResponseEvent(content="Done!", conversation_id="c1")
        bus.emit(event)

        assert len(received) == 1
        assert received[0].content == "Done!"

    def test_multiple_handlers(self):
        bus = AgentEventBus()
        calls = []

        bus.subscribe(lambda e: calls.append("h1"))
        bus.subscribe(lambda e: calls.append("h2"))

        bus.emit(ErrorEvent(error="boom"))

        assert calls == ["h1", "h2"]

    @pytest.mark.asyncio
    async def test_async_handler_is_scheduled(self):
        """Async handlers should be scheduled via create_task."""
        bus = AgentEventBus()
        results = []

        async def async_handler(event):
            await asyncio.sleep(0)  # simulate async work
            results.append(event.type)

        bus.subscribe(async_handler)

        event = ToolCallResultEvent(tool_name="test")
        bus.emit(event)

        # Give the event loop a chance to run the scheduled task
        await asyncio.sleep(0.01)

        # The handler should have received at least one event (the one we emitted)
        assert len(results) >= 1

    def test_error_isolation_in_handlers(self):
        """One bad handler should not break others or the bus."""
        bus = AgentEventBus()
        good_handler_calls = []

        def bad_handler(event):
            raise RuntimeError("Handler exploded!")

        def good_handler(event):
            good_handler_calls.append(True)

        bus.subscribe(bad_handler)
        bus.subscribe(good_handler)

        # Should not raise
        bus.emit(FinalResponseEvent(content="test"))

        assert len(good_handler_calls) == 1

    def test_unsubscribe(self):
        bus = AgentEventBus()
        calls = []

        def handler(e):
            calls.append(1)

        bus.subscribe(handler)
        bus.emit(ThinkingEvent(message="test"))

        bus.unsubscribe(handler)
        bus.emit(ThinkingEvent(message="test"))

        assert len(calls) == 1

    def test_clear(self):
        bus = AgentEventBus()
        bus.subscribe(lambda e: None)
        bus.subscribe(lambda e: None)

        assert bus.handler_count == 2
        bus.clear()
        assert bus.handler_count == 0


class TestHelixAgentEventIntegration:
    """Light integration tests with HelixAgent (without full LLM calls)."""

    def test_agent_accepts_listeners(self):
        from core.agent import HelixAgent

        received = []

        def listener(event):
            received.append(event)

        agent = HelixAgent(event_listeners=[listener], enable_monitoring=False)

        # Manually emit something
        agent.emit(ThinkingEvent(message="Test"))

        assert len(received) == 1
        assert received[0].message == "Test"

    def test_agent_has_default_event_bus(self):
        from core.agent import HelixAgent

        agent = HelixAgent(enable_monitoring=False)
        assert agent.events is not None
        assert isinstance(agent.events, AgentEventBus)


# =============================================================================
# Tests for the unified execution engine (with heavy mocking)
# =============================================================================

@pytest.mark.integration
class TestRunAgentLoopWithMocks:
    """
    These tests exercise the unified run_agent_loop using mocks so we don't
    need a real LLM or external services.
    """

    @pytest.mark.asyncio
    async def test_run_agent_loop_emits_expected_events(self, monkeypatch):
        from core.agent_execution import run_agent_loop
        from core.agent import HelixAgent
        from unittest.mock import AsyncMock, MagicMock

        # Create a minimal agent with mocked dependencies
        agent = HelixAgent(enable_monitoring=False)

        # Mock memory
        agent.memory.get_conversation = AsyncMock(return_value=[])
        agent.memory.save_message = AsyncMock()

        # Mock skills
        agent.skills.get_relevant_skills = MagicMock(return_value=[])
        agent.skills.format_skills_for_prompt = MagicMock(return_value="")

        # Mock tools
        agent.tools.get_schemas = MagicMock(return_value=[])
        agent.tools.execute = AsyncMock(return_value="Tool result here")

        # Mock LLM client to return a simple final answer (no tool calls)
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "This is the final answer."
        mock_response.choices[0].message.tool_calls = None

        agent.client.chat.completions.create = AsyncMock(return_value=mock_response)

        events = []
        async for event in run_agent_loop(agent, "Hello", "test_conv", stream=False):
            events.append(event)

        # Check that we got the important events
        event_types = [e.type for e in events]

        assert EventType.THINKING in event_types
        assert EventType.FINAL_RESPONSE in event_types

        final = next(e for e in events if isinstance(e, FinalResponseEvent))
        assert "final answer" in final.content.lower()

        # Make sure memory was used
        agent.memory.save_message.assert_called()


class TestEventCorrelation:
    def test_to_dict_includes_run_and_plan_ids(self):
        event = FinalResponseEvent(
            content="ok",
            conversation_id="conv-1",
            run_id="run-abc",
            plan_id="plan-xyz",
        )
        d = event.to_dict()
        assert d["conversation_id"] == "conv-1"
        assert d["run_id"] == "run-abc"
        assert d["plan_id"] == "plan-xyz"

    def test_agent_stamps_events_on_emit(self):
        from core.agent import HelixAgent
        from core.di.runtime_config import HelixRuntimeConfig

        cfg = HelixRuntimeConfig.from_settings()
        agent = HelixAgent(config=cfg, enable_monitoring=False)

        received: list[AgentEvent] = []
        agent.events.subscribe(received.append)

        agent.begin_run("session-42")
        agent.emit(FinalResponseEvent(content="hi"))
        agent.end_run()

        assert len(received) == 1
        assert received[0].conversation_id == "session-42"
        assert received[0].run_id
        assert len(received[0].run_id) == 12

    def test_subscribe_queue_receives_events(self):
        bus = AgentEventBus()
        queue = bus.subscribe_queue()
        bus.emit(FinalResponseEvent(content="queued", conversation_id="c1", run_id="r1"))
        assert queue.get_nowait().content == "queued"
        bus.unsubscribe_queue(queue)
