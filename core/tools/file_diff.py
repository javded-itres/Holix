"""Unified diffs for file write operations."""

from __future__ import annotations

import difflib
from pathlib import Path

DIFF_SEPARATOR = "--- diff ---"


def read_file_text(path: Path) -> str | None:
    """Return file text if readable, else None."""
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return None


def unified_diff_text(path: str, old: str, new: str, *, context: int = 3) -> str:
    """Build a unified diff string for display."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    if old and not old.endswith("\n"):
        old_lines = old.splitlines(keepends=True) or [old]
    if new and not new.endswith("\n"):
        new_lines = new.splitlines(keepends=True) or [new]

    lines = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
        n=context,
    )
    return "\n".join(lines)


def _count_diff_lines(diff: str) -> tuple[int, int]:
    added = removed = 0
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def summarize_file_write(path: str, old: str | None, new: str) -> str:
    """One-line summary for a write_file result."""
    if old is None:
        line_count = len(new.splitlines()) if new else 0
        if new and not line_count:
            line_count = 1
        return f"Created {path} (+{line_count} lines)"
    if old == new:
        return f"Updated {path} (no content changes)"

    diff = unified_diff_text(path, old, new)
    added, removed = _count_diff_lines(diff)
    return f"Updated {path} (+{added} -{removed} lines)"


def format_write_file_result(path: str, old: str | None, new: str) -> str:
    """Summary plus optional unified diff block for tool output."""
    summary = summarize_file_write(path, old, new)
    if old is not None and old == new:
        return summary

    diff = unified_diff_text(path, old or "", new)
    if not diff.strip():
        return summary
    return f"{summary}\n\n{DIFF_SEPARATOR}\n{diff}"