"""Shared graph compilation helpers."""

from __future__ import annotations

from typing import Any

from langgraph.graph import StateGraph


def compile_mode_graph(
    graph: StateGraph,
    *,
    agent: Any = None,
    checkpointer: Any = None,
    stream: bool = False,
    execution_mode: str,
):
    compiled = graph.compile(checkpointer=checkpointer)
    compiled._helix_agent = agent
    compiled._stream = stream
    compiled._execution_mode = execution_mode
    return compiled