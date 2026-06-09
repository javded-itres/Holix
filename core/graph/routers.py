"""Conditional edge routers for Helix LangGraph modes."""

from __future__ import annotations

import logging

from core.graph.state import HelixGraphState

logger = logging.getLogger(__name__)


def route_after_react(state: HelixGraphState) -> str:
    tool_calls = state.get("tool_calls", [])
    is_final = state.get("is_final", False)
    step_count = state.get("step_count", 0)
    max_steps = state.get("max_steps", 15)

    if is_final or step_count >= max_steps:
        return "finalize"
    if tool_calls:
        return "tool_execution"
    return "finalize"


def route_after_plan_execute(state: HelixGraphState) -> str:
    if state.get("is_final", False):
        return "finalize"
    plan_steps = state.get("plan_steps", [])
    current_step = state.get("current_plan_step", 0)
    return "execute_step" if current_step < len(plan_steps) else "finalize"


def route_after_plan_review(state: HelixGraphState) -> str:
    plan_status = state.get("plan_status", "pending_review")
    if plan_status == "refine":
        return "plan"
    if plan_status == "rejected":
        return "finalize"
    return "execute_step"


def route_after_plan_review_hybrid(state: HelixGraphState) -> str:
    plan_status = state.get("plan_status", "pending_review")
    if plan_status == "refine":
        return "plan"
    if plan_status == "rejected":
        return "finalize"
    return "react"


def route_after_react_plan(state: HelixGraphState) -> str:
    """Router after react_node in plan_and_execute mode."""
    tool_calls = state.get("tool_calls", [])
    is_final = state.get("is_final", False)
    is_step_complete = state.get("is_step_complete", False)
    step_count = state.get("step_count", 0)
    max_steps = state.get("max_steps", 15)
    plan_steps = state.get("plan_steps", [])
    current_step_idx = state.get("current_plan_step", 0)
    current_step_start_count = state.get("current_step_start_count", 0)

    if is_final or step_count >= max_steps:
        return "finalize"
    if tool_calls:
        return "tool_execution"
    if is_step_complete:
        return "step_orchestrate"

    has_active_plan = bool(plan_steps) and current_step_idx < len(plan_steps)
    if has_active_plan:
        max_per_step = state.get("max_steps_per_plan_step", 5)
        steps_in_current = step_count - current_step_start_count
        if steps_in_current >= max_per_step:
            logger.info(
                "Step limit reached for plan step %s: %s/%s. Advancing.",
                current_step_idx + 1,
                steps_in_current,
                max_per_step,
            )
            return "step_orchestrate"

    return "react"


def route_after_step_orchestrate(state: HelixGraphState) -> str:
    plan_steps = state.get("plan_steps", [])
    current_step_idx = state.get("current_plan_step", 0)
    if state.get("is_final", False):
        return "finalize"
    if current_step_idx < len(plan_steps):
        return "react"
    return "finalize"


def route_after_delegate_subagent(state: HelixGraphState) -> str:
    """After sub-agent delegation, continue to react for the step."""
    return "react"