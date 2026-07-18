"""Hermes-compatible SSE event formatting for gateway streams.

Implementation lives in ``core.presenters.sse`` so the agent loop does not
depend on the API package.
"""

from __future__ import annotations

from core.presenters.sse import (
    assistant_delta,
    hermes_tool_progress,
    run_completed,
    sse_data,
    sse_named,
    tool_completed,
    tool_started,
)

__all__ = [
    "assistant_delta",
    "hermes_tool_progress",
    "run_completed",
    "sse_data",
    "sse_named",
    "tool_completed",
    "tool_started",
]
