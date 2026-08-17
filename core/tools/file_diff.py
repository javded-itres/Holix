"""Unified diffs for file write operations."""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

DIFF_SEPARATOR = "--- diff ---"
CONTENT_OLD_SEPARATOR = "--- content_old ---"
CONTENT_NEW_SEPARATOR = "--- content_new ---"
# Full file sides for Studio Monaco (not needed in LLM context after strip).
_STUDIO_SIDES_MAX_CHARS = 250_000

_WRITE_SUMMARY_PATH_RE = re.compile(
    r"^(?:Created|Updated|Patched)\s+(\S+)",
    re.MULTILINE,
)


def read_file_text(path: Path, *, profile: str | None = None) -> str | None:
    """Return file text if readable, else None."""
    try:
        if not path.is_file():
            return None
        if profile:
            from core.workspace.storage import read_profile_file_text

            return read_profile_file_text(path, profile=profile)
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _diff_path_label(path: str) -> str:
    """Avoid a//abs/path in unified headers when path is absolute."""
    p = (path or "").replace("\\", "/")
    return p[1:] if p.startswith("/") else p


def unified_diff_text(path: str, old: str, new: str, *, context: int = 3) -> str:
    """Build a unified diff string for display."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    if old and not old.endswith("\n"):
        old_lines = old.splitlines(keepends=True) or [old]
    if new and not new.endswith("\n"):
        new_lines = new.splitlines(keepends=True) or [new]

    label = _diff_path_label(path)
    lines = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{label}",
        tofile=f"b/{label}",
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
        return (
            f"Updated {path} (no content changes)\n\n"
            "STOP: The file on disk is already exactly this text. "
            "Do NOT call write_file on it again. "
            "If the project files exist, run pytest once (if you have not) "
            "or give the final answer with NO tool calls so the Studio process "
            "can continue. Rewriting the same bytes is not progress."
        )

    diff = unified_diff_text(path, old, new)
    added, removed = _count_diff_lines(diff)
    return f"Updated {path} (+{added} -{removed} lines)"


def build_file_diff_payload(
    path: str,
    old: str | None,
    new: str,
    *,
    summary: str | None = None,
) -> dict[str, Any] | None:
    """Structured diff for Studio UI (path, unified, full old/new sides)."""
    if old is not None and old == new:
        return None
    unified = unified_diff_text(path, old or "", new)
    if not unified.strip():
        return None
    return {
        "path": path,
        "unified": unified,
        "old": old or "",
        "new": new,
        "summary": summary or summarize_file_write(path, old, new),
    }


def format_write_file_result(path: str, old: str | None, new: str) -> str:
    """Summary plus unified diff (+ optional full sides for Studio)."""
    summary = summarize_file_write(path, old, new)
    if old is not None and old == new:
        return summary

    diff = unified_diff_text(path, old or "", new)
    if not diff.strip():
        return summary

    body = f"{summary}\n\n{DIFF_SEPARATOR}\n{diff}"
    old_s = old or ""
    if len(old_s) + len(new) <= _STUDIO_SIDES_MAX_CHARS:
        # No extra newline between old and CONTENT_NEW so old bytes stay exact.
        body += f"\n\n{CONTENT_OLD_SEPARATOR}\n{old_s}{CONTENT_NEW_SEPARATOR}\n{new}"
    return body


def strip_studio_file_sides(result: str) -> str:
    """Remove full-file side panels so LLM/memory only keep summary + unified."""
    text = result or ""
    if CONTENT_OLD_SEPARATOR in text:
        text = text.split(CONTENT_OLD_SEPARATOR, 1)[0].rstrip()
    return text


def _split_unified_diff(unified: str) -> tuple[str, str]:
    """Best-effort reconstruction of old/new from unified diff lines (hunks only)."""
    old_lines: list[str] = []
    new_lines: list[str] = []
    for line in unified.splitlines():
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            new_lines.append(line[1:])
        elif line.startswith("-"):
            old_lines.append(line[1:])
        elif line.startswith(" "):
            old_lines.append(line[1:])
            new_lines.append(line[1:])
    return "\n".join(old_lines), "\n".join(new_lines)


def parse_tool_file_diff(result: str) -> dict[str, Any] | None:
    """Extract Studio file_diff from write_file / patch_file tool output."""
    text = result or ""
    if DIFF_SEPARATOR not in text:
        return None

    # Prefer full sides when present (accurate Monaco for updates)
    old_text: str | None = None
    new_text: str | None = None
    working = text
    if CONTENT_OLD_SEPARATOR in working and CONTENT_NEW_SEPARATOR in working:
        before_sides, _, rest = working.partition(CONTENT_OLD_SEPARATOR)
        old_part, _, new_part = rest.partition(CONTENT_NEW_SEPARATOR)
        old_text = old_part[1:] if old_part.startswith("\n") else old_part
        new_text = new_part[1:] if new_part.startswith("\n") else new_part
        working = before_sides

    summary, _, diff_block = working.partition(DIFF_SEPARATOR)
    summary = summary.strip()
    path_match = _WRITE_SUMMARY_PATH_RE.search(summary)
    if not path_match:
        return None
    path = path_match.group(1)
    # Unified block may still have content_old if parse order failed — take first section only
    unified = diff_block.strip()
    if CONTENT_OLD_SEPARATOR in unified:
        unified = unified.split(CONTENT_OLD_SEPARATOR, 1)[0].strip()
    if old_text is None or new_text is None:
        old_text, new_text = _split_unified_diff(unified)
    return {
        "path": path,
        "unified": unified,
        "old": old_text,
        "new": new_text,
        "summary": summary.split("\n")[-1].strip() if summary else summary,
    }
