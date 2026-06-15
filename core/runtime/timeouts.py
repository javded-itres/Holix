"""Shared timeout helpers for agent runs."""

from __future__ import annotations

from typing import Any

from core.graph.nodes.react_node import _llm_step_timeout_s


def agent_run_timeout_s(agent: Any, *, buffer_s: float = 120.0) -> float:
    """Upper bound for a full messenger agent run (steps + tools + finalize)."""
    cfg = getattr(agent, "config", None)
    max_steps = int(getattr(cfg, "max_steps", 90) or 90)
    step_timeout = _llm_step_timeout_s(agent)
    return step_timeout * max(1, max_steps) + buffer_s