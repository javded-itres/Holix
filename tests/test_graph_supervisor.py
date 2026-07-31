"""Tests for graph-native supervisor node and routing."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from core.graph.nodes.supervisor_node import supervisor_node
from core.graph.routers import route_after_supervisor


def test_route_after_supervisor_rework() -> None:
    assert (
        route_after_supervisor(
            {
                "supervisor_needs_rework": True,
                "supervisor_rework_tasks": [{"agent_type": "coder", "task": "x"}],
            }
        )
        == "delegate_subagent"
    )


def test_route_after_supervisor_react() -> None:
    assert (
        route_after_supervisor(
            {
                "supervisor_needs_rework": False,
                "supervisor_rework_tasks": [],
                "subagent_awaiting_synthesis": True,
            }
        )
        == "react"
    )


@pytest.mark.asyncio
async def test_supervisor_node_schedules_rework_on_failures() -> None:
    agent = MagicMock()
    agent.config = SimpleNamespace(
        subagent_supervisor_enabled=True,
        subagent_supervisor_max_interventions=2,
    )
    agent.emit = MagicMock()

    state = {
        "subagent_awaiting_synthesis": True,
        "current_subagent_wave": 1,  # collect already advanced past wave 0
        "subagent_wave_results": {
            "0": {
                "coder-1": {
                    "success": False,
                    "response": "",
                    "error": "Max steps (50) reached: hung",
                },
                "researcher-1": {
                    "success": True,
                    "response": "ok findings",
                    "error": None,
                },
            }
        },
        "subagent_task_meta": {
            "coder-1": {
                "agent_type": "coder",
                "task": "Implement auth",
                "step_ref": 1,
                "step_index": 0,
            },
            "researcher-1": {
                "agent_type": "researcher",
                "task": "Research OAuth",
                "step_ref": 1,
                "step_index": 0,
            },
        },
        "messages": [],
        "supervisor_rework_round": 0,
        "conversation_id": "t1",
    }
    config = {"configurable": {"_agent": agent}}

    out = await supervisor_node(state, config)  # type: ignore[arg-type]
    assert out["supervisor_needs_rework"] is True
    assert len(out["supervisor_rework_tasks"]) == 1
    task = out["supervisor_rework_tasks"][0]
    assert task["agent_type"] == "coder"
    assert task["prior_job"] == "coder-1"
    assert "Supervisor rework" in task["task"]
    assert out["subagent_awaiting_synthesis"] is False
    assert out["supervisor_rework_round"] == 1


@pytest.mark.asyncio
async def test_supervisor_node_ok_when_all_success() -> None:
    agent = MagicMock()
    agent.config = SimpleNamespace(subagent_supervisor_enabled=True)
    state = {
        "subagent_awaiting_synthesis": True,
        "current_subagent_wave": 1,
        "subagent_wave_results": {
            "0": {"coder-1": {"success": True, "response": "done", "error": None}}
        },
        "subagent_task_meta": {
            "coder-1": {"agent_type": "coder", "task": "x", "step_ref": 1, "step_index": 0}
        },
        "messages": [],
        "supervisor_rework_round": 0,
    }
    out = await supervisor_node(state, {"configurable": {"_agent": agent}})  # type: ignore[arg-type]
    assert out["supervisor_needs_rework"] is False
    assert out["supervisor_rework_tasks"] == []


@pytest.mark.asyncio
async def test_supervisor_node_exhausted_rework() -> None:
    agent = MagicMock()
    agent.config = SimpleNamespace(
        subagent_supervisor_enabled=True,
        subagent_supervisor_max_interventions=1,
    )
    agent.emit = MagicMock()
    state = {
        "subagent_awaiting_synthesis": True,
        "current_subagent_wave": 1,
        "subagent_wave_results": {
            "0": {"coder-1": {"success": False, "response": "", "error": "timeout"}}
        },
        "subagent_task_meta": {
            "coder-1": {"agent_type": "coder", "task": "x", "step_ref": 1, "step_index": 0}
        },
        "messages": [],
        "supervisor_rework_round": 1,  # already used max
        "conversation_id": "t1",
    }
    out = await supervisor_node(state, {"configurable": {"_agent": agent}})  # type: ignore[arg-type]
    assert out["supervisor_needs_rework"] is False
    assert out["supervisor_last_diagnosis"]["kind"] == "exhausted"
    assert any("Supervisor" in m.get("content", "") for m in out.get("messages") or [])
