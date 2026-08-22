"""Tests for Reflexion routing and reflect_node behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.graph.routers import route_after_react, route_after_react_plan, route_after_reflect
from core.meta_agent import QualityAssessment


def test_route_after_react_goes_to_reflect_on_final() -> None:
    assert (
        route_after_react(
            {
                "is_final": True,
                "tool_calls": [],
                "step_count": 3,
                "max_steps": 90,
            }
        )
        == "reflect"
    )


def test_route_after_react_tools_still_preferred() -> None:
    assert (
        route_after_react(
            {
                "is_final": False,
                "tool_calls": [{"id": "1"}],
                "step_count": 3,
                "max_steps": 90,
            }
        )
        == "tool_execution"
    )


def test_route_after_react_honesty_retry_returns_to_react() -> None:
    """Empty-tools honesty retry must not finalize via reflect."""
    assert (
        route_after_react(
            {
                "is_final": False,
                "tool_calls": [],
                "step_count": 1,
                "max_steps": 90,
                "honesty_nudge_count": 1,
                "final_response": "",
            }
        )
        == "react"
    )


def test_route_after_reflect_retry() -> None:
    assert (
        route_after_reflect(
            {
                "needs_refinement": True,
                "step_count": 5,
                "max_steps": 90,
            }
        )
        == "react"
    )


def test_route_after_reflect_finalize() -> None:
    assert route_after_reflect({"needs_refinement": False}) == "finalize"


def test_route_after_react_plan_final_to_reflect() -> None:
    assert (
        route_after_react_plan(
            {
                "is_final": True,
                "tool_calls": [],
                "step_count": 10,
                "max_steps": 90,
                "plan_steps": [{"description": "x"}],
                "current_plan_step": 0,
            }
        )
        == "reflect"
    )


@pytest.mark.asyncio
async def test_reflect_node_accepts_high_quality() -> None:
    from core.graph.nodes.reflect_node import reflect_node

    agent = MagicMock()
    agent.config = SimpleNamespace(
        enable_self_refinement=True,
        max_refinement_iterations=2,
        refinement_quality_threshold=0.7,
    )
    agent.client = MagicMock()
    agent.model = "test-model"
    agent.emit = MagicMock()
    agent.memory = MagicMock()
    agent.memory.episodic = MagicMock()
    agent.memory.episodic.store_episode = AsyncMock()

    assessment = QualityAssessment(
        quality_score=0.92,
        needs_refinement=False,
        improvement_areas=[],
        refinement_prompt="",
        reasoning="good",
    )

    with patch("core.graph.nodes.reflect_node.MetaAgent") as Meta:
        Meta.return_value.evaluate_response = AsyncMock(return_value=assessment)
        out = await reflect_node(
            {
                "final_response": "Here is a complete working solution.",
                "user_input": "Build auth",
                "messages": [],
                "reflection_count": 0,
                "max_refinement_iterations": 2,
                "conversation_id": "c1",
            },
            {"configurable": {"_agent": agent}},  # type: ignore[arg-type]
        )

    assert out["needs_refinement"] is False
    assert out.get("is_final") is not False or "is_final" not in out


@pytest.mark.asyncio
async def test_reflect_node_retries_on_low_quality() -> None:
    from core.graph.nodes.reflect_node import reflect_node

    agent = MagicMock()
    agent.config = SimpleNamespace(
        enable_self_refinement=True,
        max_refinement_iterations=2,
        refinement_quality_threshold=0.7,
    )
    agent.client = MagicMock()
    agent.model = "test-model"
    agent.emit = MagicMock()
    agent.memory = MagicMock()
    agent.memory.episodic = MagicMock()
    agent.memory.episodic.store_episode = AsyncMock()
    agent.memory.strategic = MagicMock()
    agent.memory.strategic.store_strategy = AsyncMock()

    assessment = QualityAssessment(
        quality_score=0.4,
        needs_refinement=True,
        improvement_areas=["completeness"],
        refinement_prompt="Add the missing implementation details",
        reasoning="too vague",
    )

    with patch("core.graph.nodes.reflect_node.MetaAgent") as Meta:
        Meta.return_value.evaluate_response = AsyncMock(return_value=assessment)
        out = await reflect_node(
            {
                "final_response": "Done.",
                "user_input": "Build auth",
                "messages": [],
                "reflection_count": 0,
                "max_refinement_iterations": 2,
                "conversation_id": "c1",
            },
            {"configurable": {"_agent": agent}},  # type: ignore[arg-type]
        )

    assert out["needs_refinement"] is True
    assert out["is_final"] is False
    assert out["final_response"] == ""
    assert out["reflection_count"] == 1
    msgs = out["messages"]
    assert any("Reflexion" in str(m.get("content", "")) for m in msgs)
    agent.memory.episodic.store_episode.assert_awaited()


@pytest.mark.asyncio
async def test_reflect_disabled() -> None:
    from core.graph.nodes.reflect_node import reflect_node

    agent = MagicMock()
    agent.config = SimpleNamespace(enable_self_refinement=False)
    out = await reflect_node(
        {"final_response": "x", "user_input": "y"},
        {"configurable": {"_agent": agent}},  # type: ignore[arg-type]
    )
    assert out["needs_refinement"] is False
