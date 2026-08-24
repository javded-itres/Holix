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
    if isinstance(arguments, dict) and "code" in arguments and "description" in arguments:
        # run_code: never dump the program body into TUI / messenger cards.
        return truncate_text(str(arguments.get("description") or "").strip(), max_len)
    if isinstance(arguments, dict) and "todos" in arguments:
        from core.runtime.todo_list import format_todo_summary

        return truncate_text(format_todo_summary(arguments.get("todos") or []), max_len)
    if isinstance(arguments, str):
        body = arguments
    else:
        try:
            body = json.dumps(arguments, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            body = str(arguments)
    return truncate_text(body, max_len)


def format_run_code_program_line(
    description: str,
    inner_names: list[str] | None = None,
    *,
    running: bool = False,
) -> str:
    """One-line Code mode card: description + inner tool names, no dumps."""
    desc = truncate_text((description or "").strip() or "run_code", 80)
    names = [str(n).strip() for n in (inner_names or []) if str(n).strip()]
    uniq: list[str] = list(dict.fromkeys(names))
    if not uniq:
        suffix = " …" if running else ""
        return f"🔧 программа: {desc}{suffix}"
    shown = ", ".join(uniq[:8])
    extra = f" +{len(uniq) - 8}" if len(uniq) > 8 else ""
    return f"🔧 программа: {desc} ({len(uniq)}: {shown}{extra})"


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
