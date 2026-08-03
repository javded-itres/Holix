"""Hybrid execution mode graph (plan + step orchestration + ReAct + Reflexion).

Planning path matches plan_and_execute (HOLIX.md / openspec / /init pre-scan,
plan_id stability, step checkboxes). After approval, steps run via
``step_orchestrate`` → ``react`` (same as Plan mode), with Reflexion retained
for quality loops.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from core.graph.modes._compile import compile_mode_graph
from core.graph.nodes.collect_subagent_node import collect_subagent_node
from core.graph.nodes.delegate_subagent_node import delegate_subagent_node
from core.graph.nodes.finalize_node import finalize_node
from core.graph.nodes.memory_retrieval_node import memory_retrieval_node
from core.graph.nodes.meta_agent_node import meta_agent_node
from core.graph.nodes.plan_clarify_node import plan_clarify_node
from core.graph.nodes.plan_node import plan_node
from core.graph.nodes.plan_review_node import plan_review_node
from core.graph.nodes.react_node import react_node
from core.graph.nodes.reflect_node import reflect_node
from core.graph.nodes.step_orchestrate_node import step_orchestrate_node
from core.graph.nodes.supervisor_node import supervisor_node
from core.graph.nodes.tool_execution_node import tool_execution_node
from core.graph.routers import (
    route_after_plan_clarify,
    route_after_plan_review,
    route_after_react_plan,
    route_after_reflect,
    route_after_step_orchestrate,
    route_after_supervisor,
)
from core.graph.state import HolixGraphState


def build_hybrid_graph(
    agent=None,
    checkpointer: Any = None,
    stream: bool = False,
):
    graph = StateGraph(HolixGraphState)
    graph.add_node("memory_retrieval", memory_retrieval_node)
    graph.add_node("meta_agent", meta_agent_node)
    graph.add_node("plan", plan_node)
    graph.add_node("plan_clarify", plan_clarify_node)
    graph.add_node("plan_review", plan_review_node)
    graph.add_node("step_orchestrate", step_orchestrate_node)
    graph.add_node("delegate_subagent", delegate_subagent_node)
    graph.add_node("collect_subagent", collect_subagent_node)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("react", react_node)
    graph.add_node("tool_execution", tool_execution_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "memory_retrieval")
    graph.add_edge("memory_retrieval", "meta_agent")
    graph.add_edge("meta_agent", "plan")
    graph.add_edge("plan", "plan_clarify")
    graph.add_conditional_edges(
        "plan_clarify",
        route_after_plan_clarify,
        {"plan": "plan", "plan_review": "plan_review", "finalize": "finalize"},
    )
    # Same as plan_and_execute: confirmed → step_orchestrate (not free-form react only).
    graph.add_conditional_edges(
        "plan_review",
        route_after_plan_review,
        {"plan": "plan", "execute_step": "step_orchestrate", "finalize": "finalize"},
    )
    graph.add_conditional_edges(
        "step_orchestrate",
        route_after_step_orchestrate,
        {
            "react": "react",
            "delegate_subagent": "delegate_subagent",
            "finalize": "finalize",
        },
    )
    graph.add_edge("delegate_subagent", "collect_subagent")
    graph.add_edge("collect_subagent", "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "delegate_subagent": "delegate_subagent",
            "react": "react",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "react",
        route_after_react_plan,
        {
            "tool_execution": "tool_execution",
            "step_orchestrate": "step_orchestrate",
            "reflect": "reflect",
            "finalize": "finalize",
            "react": "react",
        },
    )
    graph.add_edge("tool_execution", "react")
    graph.add_conditional_edges(
        "reflect",
        route_after_reflect,
        {"react": "react", "finalize": "finalize"},
    )
    graph.add_edge("finalize", END)

    return compile_mode_graph(
        graph,
        agent=agent,
        checkpointer=checkpointer,
        stream=stream,
        execution_mode="hybrid",
    )
