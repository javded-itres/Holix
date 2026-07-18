"""Plain-text tool formatting shared by TUI, Telegram live buffer, and CLI."""

from __future__ import annotations

import json
from typing import Any


def truncate_text(text: str, max_len: int = 500) -> str:
    raw = (text or "").strip()
    if len(raw) <= max_len:
        return raw
    return raw[: max_len - 1] + "…"


def format_tool_args(arguments: Any, *, max_len: int = 500) -> str:
    if arguments is None:
        return ""
    if isinstance(arguments, str):
        body = arguments
    else:
        try:
            body = json.dumps(arguments, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            body = str(arguments)
    return truncate_text(body, max_len)


def format_tool_header(
    tool_name: str,
    *,
    duration_s: float | None = None,
    error: bool = False,
    running: bool = False,
) -> str:
    name = tool_name or "tool"
    if running:
        return f"⎿ {name} …"
    if error:
        suffix = f" ({duration_s:.1f}s)" if duration_s is not None else ""
        return f"⎿ {name} ✗{suffix}"
    if duration_s is not None:
        return f"⎿ {name} ✓ ({duration_s:.1f}s)"
    return f"⎿ {name}"


def format_tool_result_preview(result: str, *, max_len: int = 400) -> str:
    return truncate_text(result or "", max_len)
