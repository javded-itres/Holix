"""Limits for tool output stored in conversation memory / LLM context."""

from __future__ import annotations

from typing import Any

# SQLite + session reload cap (per tool message).
DEFAULT_TOOL_MEMORY_MAX_CHARS = 16_384
# In-graph / classic loop message list sent to the LLM.
GRAPH_TOOL_MAX_CHARS = 6_000
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


def truncate_terminal_output(
    content: str,
    *,
    max_chars: int = TERMINAL_OUTPUT_MAX_CHARS,
) -> str:
    """Cap raw terminal stdout/stderr (defense in depth before hosts store it)."""
    text = content or ""
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
) -> list[dict[str, Any]]:
    """Return a copy of *messages* with oversized tool/system blobs capped.

    Used when loading history into the agent and before token usage / compress
    so a single runaway ``run_terminal_command`` cannot push context to 600%+.
    """
    if not messages:
        return messages
    out: list[dict[str, Any]] = []
    changed = False
    for msg in messages:
        role = str(msg.get("role") or "")
        content = msg.get("content")
        if role == "tool" and isinstance(content, str) and len(content) > max_chars:
            new_msg = dict(msg)
            new_msg["content"] = truncate_tool_content_for_graph(content, max_chars=max_chars)
            out.append(new_msg)
            changed = True
        else:
            out.append(msg)
    return out if changed else messages
