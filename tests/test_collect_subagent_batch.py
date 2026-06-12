"""Batch collect_subagent_node behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from core.graph.nodes.collect_subagent_node import collect_subagent_node
from core.subagents.base import (
    ProcessMode,
    SubAgentConfig,
    SubAgentHandle,
    SubAgentResult,
    SubAgentStatus,
)
from core.subagents.orchestrator import build_orchestration_plan


def _orch_state() -> dict:
    steps = [
        {
            "step": 1,
            "description": "Research",
            "tools_needed": ["web_search"],
            "depends_on": [],
            "parallel_group": None,
            "subagent_type": None,
        },
        {
            "step": 2,
            "description": "Implement module",
            "tools_needed": ["write_file"],
            "depends_on": [],
            "parallel_group": None,
            "subagent_type": None,
        },
    ]
    plan = build_orchestration_plan(
        plan_analysis={"complexity": "medium"},
        plan_steps=steps,
        enable_subagents=True,
    )
    return {
        "pending_subagents": ["web_researcher", "coder"],
        "current_subagent_wave": 0,
        "subagent_orchestration": plan.to_dict(),
        "subagent_task_meta": {
            "web_researcher": {
                "agent_type": "web_researcher",
                "task": "Research",
                "step_ref": 1,
                "step_index": 0,
            },
            "coder": {
                "agent_type": "coder",
                "task": "Implement module",
                "step_ref": 2,
                "step_index": 1,
            },
        },
        "messages": [],
    }


@pytest.mark.asyncio
async def test_collect_batch_aggregates_for_synthesis() -> None:
    agent = MagicMock()
    manager = MagicMock()

    def _handle(name: str) -> SubAgentHandle:
        return SubAgentHandle(
            name=name,
            config=SubAgentConfig(name=name, process_mode=ProcessMode.ASYNC),
            status=SubAgentStatus.COMPLETED,
        )

    async def _wait_for(name: str, timeout: float | None = None) -> SubAgentResult:
        return SubAgentResult(name=name, success=True, response=f"done:{name}")

    manager.get_handle = _handle
    manager.wait_for = AsyncMock(side_effect=_wait_for)
    agent.subagents = manager

    state = _orch_state()
    config = {"configurable": {"_agent": agent}}
    result = await collect_subagent_node(state, config)

    assert result.get("pending_subagents") == []
    assert result.get("is_step_complete") is False
    assert result.get("subagent_awaiting_synthesis") is True
    assert result.get("subagent_wave_step_indices") == [0, 1]
    assert result.get("current_subagent_wave") == 1
    content = result["messages"][-1]["content"]
    assert "Synthesize" in content
    assert "web_researcher" in content
    assert "coder" in content


def test_route_delegate_when_orchestration_pending() -> None:
    from core.graph.routers import route_after_step_orchestrate

    steps = [
        {
            "step": 1,
            "description": "Research",
            "tools_needed": ["web_search"],
            "depends_on": [],
        }
    ]
    plan = build_orchestration_plan(
        plan_analysis={"complexity": "medium"},
        plan_steps=steps,
        enable_subagents=True,
    )
    state = {
        "plan_steps": steps,
        "current_plan_step": 0,
        "subagent_orchestration": plan.to_dict(),
        "current_subagent_wave": 0,
    }
    assert route_after_step_orchestrate(state) == "delegate_subagent"