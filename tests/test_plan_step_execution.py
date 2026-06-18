"""Plan-and-execute step helpers and sub-agent routing."""

from __future__ import annotations

from core.graph.plan_step import (
    plan_step_active,
    plan_step_complete,
    prefer_non_streaming_for_plan,
)
from core.presenters.final_content import MESSENGER_EMPTY_FINAL_RU
from core.subagents.orchestrator import build_orchestration_plan, infer_subagent_type


def test_plan_step_active() -> None:
    state = {"plan_steps": [{"step": 1}], "current_plan_step": 0}
    assert plan_step_active(state)
    state["current_plan_step"] = 1
    assert not plan_step_active(state)


def test_prefer_non_streaming_during_plan_execution() -> None:
    state = {
        "execution_mode": "plan_and_execute",
        "plan_steps": [{"step": 1}],
        "current_plan_step": 0,
        "stream": True,
    }
    assert prefer_non_streaming_for_plan(state)


def test_plan_step_complete_rejects_placeholder() -> None:
    state = {"plan_steps": [{"step": 1}], "current_plan_step": 0}
    assert not plan_step_complete(state, final_response=MESSENGER_EMPTY_FINAL_RU)
    assert plan_step_complete(state, final_response="Файл создан, тесты прошли.")


def test_plan_step_complete_after_subagent_wave() -> None:
    state = {
        "plan_steps": [{"step": 1}],
        "current_plan_step": 0,
        "subagent_awaiting_synthesis": True,
    }
    assert plan_step_complete(state, final_response=MESSENGER_EMPTY_FINAL_RU)


def test_infer_subagent_from_description_at_mention() -> None:
    step = {
        "step": 1,
        "description": "Шаг 1: @coder реализует API модуль",
        "tools_needed": [],
        "subagent_type": None,
    }
    assert infer_subagent_type(step) == "coder"


def test_orchestration_enabled_for_explicit_subagent_on_simple_plan() -> None:
    steps = [
        {
            "step": 1,
            "description": "Написать сервис",
            "tools_needed": ["write_file"],
            "depends_on": [],
            "subagent_type": "coder",
        }
    ]
    plan = build_orchestration_plan(
        plan_analysis={"complexity": "simple"},
        plan_steps=steps,
        enable_subagents=True,
    )
    assert plan.enabled is True
    assert plan.waves[0].tasks[0].agent_type == "coder"