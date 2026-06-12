"""Tests for sub-agent orchestration plan builder."""

from __future__ import annotations

from core.subagents.orchestrator import (
    build_orchestration_plan,
    current_wave,
    format_wave_aggregate,
    infer_subagent_type,
)


def _step(
    num: int,
    desc: str,
    *,
    subagent_type=None,
    tools=None,
    depends_on=None,
    parallel_group=None,
) -> dict:
    return {
        "step": num,
        "description": desc,
        "tools_needed": tools or [],
        "depends_on": depends_on or [],
        "parallel_group": parallel_group,
        "subagent_type": subagent_type,
    }


def test_simple_complexity_disabled() -> None:
    plan = build_orchestration_plan(
        plan_analysis={"complexity": "simple"},
        plan_steps=[_step(1, "Research API options", tools=["web_search"])],
        enable_subagents=True,
    )
    assert plan.enabled is False


def test_medium_no_eligible_steps_disabled() -> None:
    plan = build_orchestration_plan(
        plan_analysis={"complexity": "medium"},
        plan_steps=[_step(1, "Reply with the number 42")],
        enable_subagents=True,
    )
    assert plan.enabled is False


def test_medium_single_wave_two_tasks() -> None:
    steps = [
        _step(1, "Research competitors", tools=["web_search"]),
        _step(2, "Implement API module", tools=["write_file", "terminal"]),
    ]
    plan = build_orchestration_plan(
        plan_analysis={"complexity": "medium"},
        plan_steps=steps,
        enable_subagents=True,
        max_concurrent=4,
    )
    assert plan.enabled is True
    assert len(plan.waves) == 1
    assert len(plan.waves[0].tasks) == 2
    types = {t.agent_type for t in plan.waves[0].tasks}
    assert types == {"web_researcher", "coder"}


def test_respects_max_concurrent() -> None:
    steps = [
        _step(i, f"Research topic {i}", tools=["web_search"])
        for i in range(1, 6)
    ]
    plan = build_orchestration_plan(
        plan_analysis={"complexity": "medium"},
        plan_steps=steps,
        enable_subagents=True,
        max_concurrent=2,
    )
    assert plan.enabled is True
    assert len(plan.waves[0].tasks) == 2


def test_complex_parallel_groups_create_multiple_waves() -> None:
    steps = [
        _step(1, "Research A", tools=["web_search"], parallel_group=1),
        _step(2, "Research B", tools=["web_search"], parallel_group=1),
        _step(3, "Write docs", tools=["write_file"], depends_on=[1, 2]),
    ]
    plan = build_orchestration_plan(
        plan_analysis={"complexity": "complex"},
        plan_steps=steps,
        enable_subagents=True,
    )
    assert plan.enabled is True
    assert len(plan.waves) == 2
    assert len(plan.waves[0].tasks) == 2
    assert plan.waves[1].tasks[0].agent_type == "coder"


def test_deps_block_until_completed_index() -> None:
    steps = [
        _step(1, "Build core", tools=["write_file"]),
        _step(2, "Research add-ons", tools=["web_search"], depends_on=[1]),
    ]
    plan = build_orchestration_plan(
        plan_analysis={"complexity": "medium"},
        plan_steps=steps,
        current_step_index=0,
        enable_subagents=True,
    )
    assert len(plan.waves[0].tasks) == 1
    assert plan.waves[0].tasks[0].agent_type == "coder"

    plan2 = build_orchestration_plan(
        plan_analysis={"complexity": "medium"},
        plan_steps=steps,
        current_step_index=1,
        enable_subagents=True,
    )
    assert len(plan2.waves[0].tasks) == 1
    assert plan2.waves[0].tasks[0].agent_type == "web_researcher"


def test_explicit_subagent_type() -> None:
    step = _step(1, "Do something", subagent_type="reviewer")
    assert infer_subagent_type(step) == "reviewer"


def test_format_wave_aggregate() -> None:
    from core.subagents.orchestrator import SubagentTask

    meta = {
        "reviewer-1": SubagentTask("reviewer", "review code", 1, 0),
    }
    text = format_wave_aggregate(
        wave_id=0,
        total_waves=1,
        results={"reviewer-1": {"success": True, "response": "LGTM"}},
        task_meta=meta,
    )
    assert "wave 1/1" in text
    assert "reviewer-1" in text
    assert "LGTM" in text
    assert "Synthesize" in text


def test_current_wave_accessor() -> None:
    plan = build_orchestration_plan(
        plan_analysis={"complexity": "medium"},
        plan_steps=[_step(1, "Research", tools=["web_search"])],
        enable_subagents=True,
    )
    wave = current_wave(plan, 0)
    assert wave is not None
    assert len(wave.tasks) == 1