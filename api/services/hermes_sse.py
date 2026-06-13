"""Hermes-compatible SSE event formatting for gateway streams."""

from __future__ import annotations

import json
from typing import Any


def sse_data(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def sse_named(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def assistant_delta(content: str) -> str:
    return sse_data({"type": "assistant.delta", "content": content})


def tool_started(tool: str, *, call_id: str | None = None) -> str:
    payload: dict[str, Any] = {"type": "tool.started", "tool": tool}
    if call_id:
        payload["call_id"] = call_id
    return sse_data(payload)


def tool_completed(tool: str, *, result_preview: str = "") -> str:
    return sse_data({
        "type": "tool.completed",
        "tool": tool,
        "result": result_preview[:200],
    })


def hermes_tool_progress(tool: str) -> str:
    return sse_named("hermes.tool.progress", {"tool": tool, "status": "started"})


def run_completed(**extra: Any) -> str:
    return sse_data({"type": "run.completed", **extra})