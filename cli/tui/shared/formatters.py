"""Strict TUI text formatting (unit-testable, no Textual).

Plain tool formatters live in ``core.presenters.tool_format``; this module
adds TUI-only helpers (diff render).
"""

from __future__ import annotations

from core.presenters.tool_format import (
    format_tool_args,
    format_tool_header,
    format_tool_result_preview,
    truncate_text,
)
from core.tools.file_diff import DIFF_SEPARATOR

__all__ = [
    "format_tool_args",
    "format_tool_header",
    "format_tool_result_preview",
    "format_write_file_diff_display",
    "format_write_file_result_preview",
    "split_write_file_result",
    "truncate_text",
]


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