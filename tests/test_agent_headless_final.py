"""Headless agent.run must capture FinalResponseEvent emitted only on the event bus."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from core.agent_events import FinalResponseEvent


@pytest.mark.asyncio
async def test_run_with_graph_uses_bus_emitted_final_response() -> None:
    agent = MagicMock()
    agent._use_langgraph = True
    agent._execution_mode_last = None
    agent._graph = None
    agent.config = MagicMock()
    agent.config.execution_mode = "react"
    agent._initialized = True
    agent._event_context = None
    agent._final_response_emitted = False
    agent.stamp_event = lambda event: event

    from core.agent_events import AgentEventBus

    agent.events = AgentEventBus()

    def _emit(event):
        agent.events.emit(event)

    agent.emit = _emit

    async def _fake_run_holix(_agent, _user_input, _conversation_id, **kwargs):
        _emit(
            FinalResponseEvent(
                content="Привет! Как дела?",
                steps_taken=1,
                conversation_id=_conversation_id,
            )
        )
        if False:  # pragma: no cover
            yield

    with patch("core.runtime.executor.run_holix", side_effect=_fake_run_holix):
        from core.agent import HolixAgent

        result = await HolixAgent._run_with_graph(
            agent,
            "cron task",
            conversation_id="cron-test",
            execution_mode="react",
        )

    assert result == "Привет! Как дела?"