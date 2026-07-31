"""ReAct execution mode graph with meta-agent + Reflexion cycle."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from core.graph.modes._compile import compile_mode_graph
from core.graph.nodes.finalize_node import finalize_node
from core.graph.nodes.memory_retrieval_node import memory_retrieval_node
from core.graph.nodes.meta_agent_node import meta_agent_node
from core.graph.nodes.react_node import react_node
from core.graph.nodes.reflect_node import reflect_node
from core.graph.nodes.tool_execution_node import tool_execution_node
from core.graph.routers import route_after_react, route_after_reflect
from core.graph.state import HolixGraphState


def build_react_graph(
    agent=None,
    checkpointer: Any = None,
    stream: bool = False,
):
    graph = StateGraph(HolixGraphState)
    graph.add_node("memory_retrieval", memory_retrieval_node)
    graph.add_node("meta_agent", meta_agent_node)
    graph.add_node("react", react_node)
    graph.add_node("tool_execution", tool_execution_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "memory_retrieval")
    graph.add_edge("memory_retrieval", "meta_agent")
    graph.add_edge("meta_agent", "react")
    graph.add_conditional_edges(
        "react",
        route_after_react,
        {
            "tool_execution": "tool_execution",
            "reflect": "reflect",
            "finalize": "finalize",
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
        execution_mode="react",
    )
