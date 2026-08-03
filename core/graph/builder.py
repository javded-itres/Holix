"""
Graph Builder — composes Holix LangGraph execution graphs by mode.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.graph.modes.hybrid import build_hybrid_graph
from core.graph.modes.plan_execute import build_plan_and_execute_graph
from core.graph.modes.react import build_react_graph
from core.persistence import async_checkpointer, create_checkpointer

logger = logging.getLogger(__name__)

_MODE_BUILDERS = {
    "react": build_react_graph,
    "plan_and_execute": build_plan_and_execute_graph,
    "hybrid": build_hybrid_graph,
}


def build_holix_graph(
    agent=None,
    execution_mode: str = "react",
    checkpointer: Any = None,
    stream: bool = False,
):
    """Build the Holix LangGraph execution graph for the given mode."""
    builder = _MODE_BUILDERS.get(execution_mode, build_react_graph)
    return builder(agent=agent, checkpointer=checkpointer, stream=stream)


def prepare_initial_state(
    agent,
    user_input: str,
    conversation_id: str = "default",
    stream: bool = False,
    execution_mode: str = "react",
    *,
    state_overrides: dict | None = None,
) -> dict:
    """Prepare initial HolixGraphState for a graph invocation.

    ``state_overrides`` merges on top (used to resume a confirmed plan without
    re-running planning / review).
    """
    cfg = getattr(agent, "config", None)
    max_steps = cfg.max_steps if cfg else 90
    max_per_step = cfg.max_steps_per_plan_step if cfg else 5
    max_refinement = cfg.max_refinement_iterations if cfg else 2

    state: dict[str, Any] = {
        "user_input": user_input,
        "conversation_id": conversation_id,
        "stream": stream,
        "messages": [],
        "system_prompt": "",
        "tool_calls": [],
        "tool_results": [],
        "relevant_memories": [],
        "relevant_skills": [],
        "relevant_strategies": [],
        "step_count": 0,
        "max_steps": max_steps,
        "base_max_steps": max_steps,
        "step_budget_extensions": 0,
        "max_steps_per_plan_step": max_per_step,
        "execution_mode": execution_mode,
        "is_final": False,
        "final_response": "",
        "meta_decision": None,
        "needs_refinement": False,
        "refinement_iterations": 0,
        "max_refinement_iterations": max_refinement,
        "reflection_count": 0,
        "reflection_log": [],
        "plan_steps": [],
        "current_plan_step": 0,
        "plan_status": "pending_review",
        "plan_review_id": "",
        "plan_id": "",
        "plan_refinement_feedback": "",
        "plan_clarification_rounds": 0,
        "is_step_complete": False,
        "current_step_start_count": 0,
        "plan_analysis": None,
        "plan_architecture": None,
        "plan_report": None,
        "plan_reasoning": "",
        "sub_agent_tasks": [],
        "sub_agent_results": {},
        "pending_subagent": None,
        # Per user turn (must reset: checkpoint otherwise freezes honesty forever)
        "honesty_nudge_count": 0,
        "supervisor_needs_rework": False,
        "supervisor_rework_tasks": [],
        "supervisor_rework_round": 0,
        "supervisor_log": [],
        "supervisor_last_diagnosis": None,
    }
    if state_overrides:
        for key, value in state_overrides.items():
            if value is not None or key in (
                "plan_analysis",
                "plan_architecture",
                "plan_report",
            ):
                state[key] = value
    return state


async def run_graph_loop(
    agent,
    user_input: str,
    conversation_id: str = "default",
    *,
    stream: bool = False,
    execution_mode: str = "react",
    state_overrides: dict | None = None,
):
    """Run the Holix graph and translate state transitions to AgentEvents."""
    from core.agent_events import (
        ErrorEvent,
        FinalResponseEvent,
        MaxStepsReachedEvent,
        ThinkingEvent,
    )
    from core.graph.modes.router import ModeRouter
    from core.presenters.final_content import is_placeholder_final
    from core.runtime.session import prepare_session

    # Resume path: confirmed plan in overrides → always plan_and_execute
    # (step_orchestrate + checkboxes), even if UI mode is hybrid/auto/react.
    resume_plan = bool(
        state_overrides
        and (state_overrides.get("plan_steps") or [])
        and str(state_overrides.get("plan_status") or "").lower()
        in ("confirmed", "auto_execute", "in_progress")
    )
    selected_by_auto: str | None = None
    if resume_plan:
        execution_mode = "plan_and_execute"
    elif execution_mode == "auto":
        mode_router = ModeRouter(client=agent.client, model=getattr(agent, "model", "") or "")
        selected_by_auto = await mode_router.select_mode(
            user_input,
            context={"relevant_strategies": [], "relevant_memories": []},
            agent=agent,
            conversation_id=conversation_id,
        )
        execution_mode = selected_by_auto or "react"

    messages, _was_compressed = await prepare_session(agent, user_input, conversation_id)

    initial_state = prepare_initial_state(
        agent,
        user_input,
        conversation_id,
        stream,
        execution_mode,
        state_overrides=state_overrides,
    )
    initial_state["messages"] = messages
    # Keep resolved mode on state so plan_node / react see hybrid vs plan_and_execute.
    initial_state["execution_mode"] = execution_mode

    cfg = getattr(agent, "config", None)
    use_persistent = bool(
        cfg
        and getattr(cfg, "use_langgraph", True)
        and getattr(cfg, "langgraph_checkpoint_db_path", None)
    )
    db_path = cfg.langgraph_checkpoint_db_path if cfg else None

    from core.i18n.live_ui import live_holix_thinking_label
    from core.profile.soul import profile_name_from_agent

    mode_label = {
        "react": "ReAct",
        "plan_and_execute": "Plan & Execute",
        "hybrid": "Hybrid",
    }.get(execution_mode, execution_mode)
    if selected_by_auto:
        mode_label = f"Auto → {mode_label}"

    profile_name = profile_name_from_agent(agent) if agent else "default"
    yield ThinkingEvent(
        message=live_holix_thinking_label(profile_name, mode_label),
        conversation_id=conversation_id,
    )
    if selected_by_auto:
        yield ThinkingEvent(
            message=f"Auto mode selected: {selected_by_auto}",
            conversation_id=conversation_id,
        )

    from core.domain.graph_runtime import GraphRuntime

    graph_runtime = GraphRuntime.from_agent(agent) if agent is not None else None
    config = {
        "configurable": {
            "thread_id": conversation_id,
            "_agent": agent,
            "_runtime": graph_runtime,
        },
    }

    try:
        async with async_checkpointer(
            use_persistent=use_persistent,
            db_path=db_path,
        ) as checkpointer:
            compiled_graph = build_holix_graph(
                agent=agent,
                execution_mode=execution_mode,
                checkpointer=checkpointer,
                stream=stream,
            )
            final_state = await compiled_graph.ainvoke(initial_state, config)

        final_text = (final_state.get("final_response") or "").strip()
        if (
            final_text
            and not is_placeholder_final(final_text)
            and not getattr(agent, "_final_response_emitted", False)
        ):
            yield FinalResponseEvent(
                content=final_text,
                steps_taken=final_state.get("step_count", 0),
                conversation_id=conversation_id,
            )

        step_count = final_state.get("step_count", 0)
        max_steps = final_state.get("max_steps", 90)
        if step_count >= max_steps and not final_state.get("is_final", False):
            yield MaxStepsReachedEvent(
                max_steps=max_steps,
                conversation_id=conversation_id,
            )
            timeout_msg = f"Agent reached maximum steps ({max_steps}). Task may be too complex."
            await agent.memory.save_message(conversation_id, "assistant", timeout_msg)

    except asyncio.CancelledError:
        raise
    except RuntimeError as e:
        # LangGraph / LLM stream cleanup after cancel or wait_for timeout.
        if "generator didn't stop after athrow" in str(e):
            # Prefer the real failure (e.g. PermissionError while building the
            # prompt) over a silent cancel — otherwise Studio looks "hung".
            root = e.__cause__ or e.__context__
            if root is not None and not isinstance(root, asyncio.CancelledError):
                yield ErrorEvent(
                    error=f"Error during graph execution: {root}",
                    error_type="execution",
                    recoverable=False,
                    conversation_id=conversation_id,
                )
                return
            raise asyncio.CancelledError() from e
        yield ErrorEvent(
            error=f"Error during graph execution: {str(e)}",
            error_type="execution",
            recoverable=False,
            conversation_id=conversation_id,
        )
    except Exception as e:
        yield ErrorEvent(
            error=f"Error during graph execution: {str(e)}",
            error_type="execution",
            recoverable=False,
            conversation_id=conversation_id,
        )


def build_react_graph_for_studio():
    """LangGraph Studio entry point for ReAct mode."""
    return build_react_graph(agent=None, checkpointer=create_checkpointer())


def build_plan_execute_graph_for_studio():
    """LangGraph Studio entry point for plan-and-execute mode."""
    return build_plan_and_execute_graph(agent=None, checkpointer=create_checkpointer())


# Re-export routers for backward compatibility
from core.graph.routers import (  # noqa: E402
    route_after_plan_clarify,
    route_after_plan_execute,
    route_after_plan_review,
    route_after_plan_review_hybrid,  # legacy alias; hybrid graph uses route_after_plan_review
    route_after_react,
    route_after_react_plan,
    route_after_step_orchestrate,
)

__all__ = [
    "build_holix_graph",
    "build_react_graph",
    "build_plan_and_execute_graph",
    "build_hybrid_graph",
    "prepare_initial_state",
    "run_graph_loop",
    "route_after_react",
    "route_after_plan_execute",
    "route_after_plan_clarify",
    "route_after_plan_review",
    "route_after_plan_review_hybrid",
    "route_after_react_plan",
    "route_after_step_orchestrate",
]