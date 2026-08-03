"""Resume confirmed plans without re-planning / re-review."""

from __future__ import annotations

import asyncio

import pytest

from core.graph.builder import prepare_initial_state
from core.graph.nodes.plan_clarify_node import plan_clarify_node
from core.graph.nodes.plan_node import plan_node
from core.graph.nodes.plan_review_node import plan_review_node


def test_prepare_initial_state_overrides_confirmed_plan() -> None:
    steps = [
        {"step": 1, "description": "A", "status": "done"},
        {"step": 2, "description": "B", "status": "pending"},
    ]
    state = prepare_initial_state(
        None,
        "resume task",
        "cid",
        execution_mode="plan_and_execute",
        state_overrides={
            "plan_id": "plan_abc",
            "plan_steps": steps,
            "current_plan_step": 1,
            "plan_status": "confirmed",
        },
    )
    assert state["plan_status"] == "confirmed"
    assert state["plan_id"] == "plan_abc"
    assert state["current_plan_step"] == 1
    assert len(state["plan_steps"]) == 2


@pytest.mark.asyncio
async def test_plan_node_skips_generation_when_confirmed() -> None:
    steps = [{"step": 1, "description": "Existing", "status": "pending"}]
    state = {
        "user_input": "should not replan",
        "conversation_id": "c1",
        "plan_steps": steps,
        "plan_status": "confirmed",
        "plan_id": "plan_keep",
        "current_plan_step": 0,
        "plan_refinement_feedback": "",
        "plan_analysis": {"task_summary": "x"},
        "plan_architecture": None,
        "plan_report": None,
        "plan_reasoning": "keep",
    }
    out = await plan_node(state, {"configurable": {"_agent": None}})
    assert out["plan_status"] == "confirmed"
    assert out["plan_id"] == "plan_keep"
    assert out["plan_steps"][0]["description"] == "Existing"
    # No brand-new single-step scaffold of the user_input
    assert out["plan_steps"][0]["description"] != "should not replan"


@pytest.mark.asyncio
async def test_plan_clarify_preserves_confirmed_status() -> None:
    state = {
        "plan_status": "confirmed",
        "plan_steps": [{"step": 1, "description": "x"}],
        "plan_analysis": None,
        "plan_report": None,
        "conversation_id": "c",
        "user_input": "t",
        "plan_clarification_rounds": 0,
    }
    out = await plan_clarify_node(state, {"configurable": {"_agent": None}})
    assert out == {}


@pytest.mark.asyncio
async def test_plan_review_skips_when_confirmed() -> None:
    state = {
        "plan_status": "confirmed",
        "plan_steps": [{"step": 1, "description": "x"}],
        "conversation_id": "c",
        "user_input": "t",
    }
    out = await plan_review_node(state, {"configurable": {"_agent": None}})
    assert out == {}
