"""Strict TUI text formatting (unit-testable, no Textual)."""

from __future__ import annotations

import json
from typing import Any

from core.tools.file_diff import DIFF_SEPARATOR


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


def split_write_file_result(result: str) -> tuple[str, str | None]:
    """Split write_file tool output into summary and unified diff text."""
    body = result or ""
    marker = f"\n{DIFF_SEPARATOR}\n"
    if marker in body:
        summary, diff = body.split(marker, 1)
        return summary.strip(), diff.strip() or None
    return body.strip(), None


def format_write_file_diff_display(diff: str, *, path: str = ""):
    """Rich renderable for a unified diff in the transcript."""
    from cli.tui.shared.diff_render import render_unified_diff

    return render_unified_diff(diff, path=path)


def format_write_file_result_preview(result: str, *, max_len: int = 400) -> str:
    """Preview for write_file: show summary only (diff rendered separately)."""
    summary, _ = split_write_file_result(result)
    return truncate_text(summary, max_len)