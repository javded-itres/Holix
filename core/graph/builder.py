"""
Graph Builder — composes Holix LangGraph execution graphs by mode.
"""

from __future__ import annotations

import logging
from typing import Any

from core.graph.modes.hybrid import build_hybrid_graph
from core.graph.modes.plan_execute import build_plan_and_execute_graph
from core.graph.modes.react import build_react_graph
from core.persistence import create_checkpointer

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
) -> dict:
    """Prepare initial HolixGraphState for a graph invocation."""
    cfg = getattr(agent, "config", None)
    max_steps = cfg.max_steps if cfg else 15
    max_per_step = cfg.max_steps_per_plan_step if cfg else 5
    max_refinement = cfg.max_refinement_iterations if cfg else 2

    return {
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
        "max_steps_per_plan_step": max_per_step,
        "execution_mode": execution_mode,
        "is_final": False,
        "final_response": "",
        "meta_decision": None,
        "needs_refinement": False,
        "refinement_iterations": 0,
        "max_refinement_iterations": max_refinement,
        "plan_steps": [],
        "current_plan_step": 0,
        "plan_status": "pending_review",
        "plan_review_id": "",
        "plan_id": "",
        "plan_refinement_feedback": "",
        "is_step_complete": False,
        "current_step_start_count": 0,
        "plan_analysis": None,
        "plan_architecture": None,
        "sub_agent_tasks": [],
        "sub_agent_results": {},
        "pending_subagent": None,
    }


async def run_graph_loop(
    agent,
    user_input: str,
    conversation_id: str = "default",
    *,
    stream: bool = False,
    execution_mode: str = "react",
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

    if execution_mode == "auto":
        mode_router = ModeRouter(client=agent.client)
        execution_mode = await mode_router.select_mode(
            user_input,
            context={"relevant_strategies": [], "relevant_memories": []},
        )

    messages, _was_compressed = await prepare_session(agent, user_input, conversation_id)

    initial_state = prepare_initial_state(
        agent, user_input, conversation_id, stream, execution_mode
    )
    initial_state["messages"] = messages

    cfg = getattr(agent, "config", None)
    checkpointer = create_checkpointer(
        use_persistent=bool(cfg and cfg.use_langgraph),
        db_path=cfg.langgraph_checkpoint_db_path if cfg else None,
    )

    compiled_graph = build_holix_graph(
        agent=agent,
        execution_mode=execution_mode,
        checkpointer=checkpointer,
        stream=stream,
    )

    from core.i18n.live_ui import live_holix_thinking_label
    from core.profile.soul import profile_name_from_agent

    mode_label = {
        "react": "ReAct",
        "plan_and_execute": "Plan & Execute",
        "hybrid": "Hybrid",
    }.get(execution_mode, execution_mode)

    profile_name = profile_name_from_agent(agent) if agent else "default"
    yield ThinkingEvent(
        message=live_holix_thinking_label(profile_name, mode_label),
        conversation_id=conversation_id,
    )

    config = {
        "configurable": {
            "thread_id": conversation_id,
            "_agent": agent,
        },
    }

    try:
        final_state = await compiled_graph.ainvoke(initial_state, config)

        final_text = (final_state.get("final_response") or "").strip()
        if final_text and not is_placeholder_final(final_text):
            yield FinalResponseEvent(
                content=final_text,
                steps_taken=final_state.get("step_count", 0),
                conversation_id=conversation_id,
            )

        step_count = final_state.get("step_count", 0)
        max_steps = final_state.get("max_steps", 15)
        if step_count >= max_steps and not final_state.get("is_final", False):
            yield MaxStepsReachedEvent(
                max_steps=max_steps,
                conversation_id=conversation_id,
            )
            timeout_msg = f"Agent reached maximum steps ({max_steps}). Task may be too complex."
            await agent.memory.save_message(conversation_id, "assistant", timeout_msg)

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
    route_after_plan_execute,
    route_after_plan_review,
    route_after_plan_review_hybrid,
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
    "route_after_plan_review",
    "route_after_plan_review_hybrid",
    "route_after_react_plan",
    "route_after_step_orchestrate",
]