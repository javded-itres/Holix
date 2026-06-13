"""Plan-and-execute execution mode graph."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from core.graph.modes._compile import compile_mode_graph
from core.graph.nodes.collect_subagent_node import collect_subagent_node
from core.graph.nodes.delegate_subagent_node import delegate_subagent_node
from core.graph.nodes.finalize_node import finalize_node
from core.graph.nodes.memory_retrieval_node import memory_retrieval_node
from core.graph.nodes.plan_node import plan_node
from core.graph.nodes.plan_review_node import plan_review_node
from core.graph.nodes.react_node import react_node
from core.graph.nodes.step_orchestrate_node import step_orchestrate_node
from core.graph.nodes.tool_execution_node import tool_execution_node
from core.graph.routers import (
    route_after_plan_review,
    route_after_react_plan,
    route_after_step_orchestrate,
)
from core.graph.state import HolixGraphState


def build_plan_and_execute_graph(
    agent=None,
    checkpointer: Any = None,
    stream: bool = False,
):
    graph = StateGraph(HolixGraphState)
    graph.add_node("memory_retrieval", memory_retrieval_node)
    graph.add_node("plan", plan_node)
    graph.add_node("plan_review", plan_review_node)
    graph.add_node("step_orchestrate", step_orchestrate_node)
    graph.add_node("delegate_subagent", delegate_subagent_node)
    graph.add_node("collect_subagent", collect_subagent_node)
    graph.add_node("react", react_node)
    graph.add_node("tool_execution", tool_execution_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "memory_retrieval")
    graph.add_edge("memory_retrieval", "plan")
    graph.add_edge("plan", "plan_review")
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
    graph.add_edge("collect_subagent", "react")
    graph.add_conditional_edges(
        "react",
        route_after_react_plan,
        {
            "tool_execution": "tool_execution",
            "step_orchestrate": "step_orchestrate",
            "finalize": "finalize",
            "react": "react",
        },
    )
    graph.add_edge("tool_execution", "react")
    graph.add_edge("finalize", END)

    return compile_mode_graph(
        graph,
        agent=agent,
        checkpointer=checkpointer,
        stream=stream,
        execution_mode="plan_and_execute",
    )