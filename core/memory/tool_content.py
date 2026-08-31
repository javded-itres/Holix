"""Limits for tool output stored in conversation memory / LLM context."""

from __future__ import annotations

import re
from typing import Any

_DEBUG_LOG_LINE = re.compile(r"^(?:DEBUG|TRACE)\b")

# SQLite + session reload cap (per tool message).
DEFAULT_TOOL_MEMORY_MAX_CHARS = 16_384
# In-graph / classic loop message list sent to the LLM (recent tools).
GRAPH_TOOL_MAX_CHARS = 6_000
# Older tool messages in the same turn window — keep a pointer, not the dump.
STALE_TOOL_MAX_CHARS = 1_200
# How many trailing tool messages keep the full graph cap.
RECENT_TOOL_KEEP = 6
# Hard cap at tool execution (stdout+stderr) before any host path sees it.
TERMINAL_OUTPUT_MAX_CHARS = 32_768


def _prepare_tool_content(content: str) -> str:
    """Drop Studio-only full-file sides before LLM/memory storage."""
    try:
        from core.tools.file_diff import strip_studio_file_sides

        return strip_studio_file_sides(content or "")
    except Exception:
        return content or ""


def truncate_tool_content_for_memory(
    content: str,
    *,
    max_chars: int = DEFAULT_TOOL_MEMORY_MAX_CHARS,
) -> str:
    """Truncate oversized tool output before persisting to SQLite/ChromaDB."""
    content = _prepare_tool_content(content)
    if not content or len(content) <= max_chars:
        return content
    return content[:max_chars] + f"\n\n… [truncated for memory; total {len(content):,} chars]"


def truncate_tool_content_for_graph(
    content: str,
    *,
    max_chars: int = GRAPH_TOOL_MAX_CHARS,
) -> str:
    """Truncate tool output stored in the LangGraph message list (LLM context)."""
    content = _prepare_tool_content(content)
    if not content or len(content) <= max_chars:
        return content
    return (
        content[:max_chars] + f"\n\n… [truncated for context; total {len(content):,} chars; "
        "re-read file if you need more]"
    )


def strip_debug_log_lines(content: str) -> str:
    """Drop logging DEBUG/TRACE lines so pytest dumps stay readable."""
    text = content or ""
    if "DEBUG" not in text and "TRACE" not in text:
        return text
    kept: list[str] = []
    dropped = 0
    for line in text.splitlines():
        if _DEBUG_LOG_LINE.match(line.lstrip()):
            dropped += 1
            continue
        kept.append(line)
    if dropped == 0:
        return text
    out = "\n".join(kept)
    note = f"\n… [{dropped} verbose log lines omitted]"
    return (out + note) if out else note.strip()


def truncate_terminal_output(
    content: str,
    *,
    max_chars: int = TERMINAL_OUTPUT_MAX_CHARS,
) -> str:
    """Cap raw terminal stdout/stderr (defense in depth before hosts store it)."""
    text = strip_debug_log_lines(content or "")
    if len(text) <= max_chars:
        return text
    return (
        text[:max_chars] + f"\n\n… [truncated terminal output; total {len(text):,} chars; "
        "narrow the command or use read_file for specific paths]"
    )


def sanitize_messages_tool_content(
    messages: list[dict[str, Any]],
    *,
    max_chars: int = GRAPH_TOOL_MAX_CHARS,
    stale_max_chars: int = STALE_TOOL_MAX_CHARS,
    recent_tool_keep: int = RECENT_TOOL_KEEP,
) -> list[dict[str, Any]]:
    """Return a copy of *messages* with oversized tool blobs capped.

    The last ``recent_tool_keep`` tool messages keep ``max_chars``. Older tool
    results are cut to ``stale_max_chars`` so a long apply/debug loop does not
    keep every grep/log dump at full size until 85% of the window.
    """
    if not messages:
        return messages
    tool_indexes = [
        i
        for i, msg in enumerate(messages)
        if str(msg.get("role") or "") == "tool" and isinstance(msg.get("content"), str)
    ]
    keep = max(0, int(recent_tool_keep))
    recent = set(tool_indexes[-keep:]) if keep else set()
    out: list[dict[str, Any]] = []
    changed = False
    stale_cap = max(200, int(stale_max_chars))
    recent_cap = max(stale_cap, int(max_chars))
    for i, msg in enumerate(messages):
        role = str(msg.get("role") or "")
        content = msg.get("content")
        if role != "tool" or not isinstance(content, str):
            out.append(msg)
            continue
        cap = recent_cap if i in recent else stale_cap
        if len(content) <= cap:
            out.append(msg)
            continue
        new_msg = dict(msg)
        new_msg["content"] = truncate_tool_content_for_graph(content, max_chars=cap)
        out.append(new_msg)
        changed = True
    return out if changed else messages
