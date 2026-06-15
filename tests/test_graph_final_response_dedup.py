"""FinalResponseEvent must not be emitted twice per react run."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.agent_events import FinalResponseEvent


@pytest.mark.asyncio
async def test_run_graph_loop_skips_duplicate_final_response() -> None:
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
    agent._final_response_emitted = True
    agent.memory = AsyncMock()
    agent.memory.get_conversation = AsyncMock(return_value=[])
    agent.emit = MagicMock()

    final_state = {
        "final_response": "Готово.",
        "step_count": 1,
        "is_final": True,
    }

    with (
        patch("core.runtime.session.prepare_session", new_callable=AsyncMock) as prep,
        patch("core.graph.builder.create_checkpointer") as cp,
        patch("core.graph.builder.build_holix_graph") as build_graph,
    ):
        prep.return_value = ([{"role": "user", "content": "hi"}], False)
        cp.return_value = None
        compiled = MagicMock()
        compiled.ainvoke = AsyncMock(return_value=final_state)
        build_graph.return_value = compiled

        from core.graph.builder import run_graph_loop

        events = [
            e
            async for e in run_graph_loop(
                agent,
                "hi",
                "conv-1",
                stream=False,
                execution_mode="react",
            )
        ]

    final_events = [e for e in events if isinstance(e, FinalResponseEvent)]
    assert len(final_events) == 0