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


@pytest.mark.asyncio
async def test_run_graph_loop_emits_empty_final_when_honesty_cleared_response() -> None:
    """Messengers need FinalResponseEvent even if honesty retries left text empty."""
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
        "final_response": "",
        "step_count": 3,
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
                "tg_pavel_1",
                stream=True,
                execution_mode="react",
            )
        ]

    final_events = [e for e in events if isinstance(e, FinalResponseEvent)]
    assert len(final_events) == 1
    assert final_events[0].content == ""
    assert agent._final_response_emitted is True


@pytest.mark.asyncio
async def test_run_graph_loop_fills_empty_final_from_tool_results() -> None:
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
        "final_response": "",
        "step_count": 2,
        "is_final": True,
        "tool_results": [
            {
                "tool_name": "mcp_holix_studio_projects_list_tool",
                "result": (
                    '{"ok": true, "projects": [], "sdd_projects": '
                    '[{"path": "projects/shop_api", "label": "shop_api", '
                    '"kind": "sdd"}]}'
                ),
            }
        ],
    }

    with (
        patch("core.runtime.session.prepare_session", new_callable=AsyncMock) as prep,
        patch("core.graph.builder.create_checkpointer") as cp,
        patch("core.graph.builder.build_holix_graph") as build_graph,
    ):
        prep.return_value = ([{"role": "user", "content": "какие проекты?"}], False)
        cp.return_value = None
        compiled = MagicMock()
        compiled.ainvoke = AsyncMock(return_value=final_state)
        build_graph.return_value = compiled

        from core.graph.builder import run_graph_loop

        events = [
            e
            async for e in run_graph_loop(
                agent,
                "какие проекты?",
                "tg_pavel_1",
                stream=True,
                execution_mode="react",
            )
        ]

    final_events = [e for e in events if isinstance(e, FinalResponseEvent)]
    assert len(final_events) == 1
    assert "shop_api" in final_events[0].content
    assert "{" not in final_events[0].content
