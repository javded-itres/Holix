"""Helpers for plan-and-execute step orchestration in react_node."""

from __future__ import annotations

from typing import Any

from core.presenters.final_content import is_meaningful_final_response

_PLAN_STEP_NUDGE = (
    "[Plan executor] This step requires visible progress via tool calls "
    "(write_file, terminal, web_search, etc.). Do not reply with reasoning "
    "only — execute the step and use tools now."
)


def plan_step_active(state: dict[str, Any]) -> bool:
    plan_steps = state.get("plan_steps") or []
    current = int(state.get("current_plan_step", 0))
    return bool(plan_steps) and current < len(plan_steps)


def prefer_non_streaming_for_plan(state: dict[str, Any]) -> bool:
    """Reasoning models often hang in streaming during plan step execution."""
    if state.get("execution_mode") != "plan_and_execute":
        return False
    return plan_step_active(state) or bool(state.get("subagent_awaiting_synthesis"))


def plan_step_complete(
    state: dict[str, Any],
    *,
    final_response: str,
) -> bool:
    if state.get("subagent_awaiting_synthesis"):
        return True
    return is_meaningful_final_response(final_response)


def plan_step_retry_update(
    *,
    messages: list[dict[str, Any]],
    step_count: int,
    final_response: str,
    include_assistant: bool = True,
) -> dict[str, Any]:
    """Keep the current plan step open and nudge the model to use tools."""
    updated = list(messages)
    if include_assistant and final_response:
        updated.append({"role": "assistant", "content": final_response})
    updated.append({"role": "user", "content": _PLAN_STEP_NUDGE})
    return {
        "messages": updated,
        "step_count": step_count,
        "is_final": False,
        "is_step_complete": False,
        "tool_calls": [],
        "final_response": final_response,
    }