"""Limits for tool output stored in conversation memory."""

from __future__ import annotations

DEFAULT_TOOL_MEMORY_MAX_CHARS = 16_384
GRAPH_TOOL_MAX_CHARS = 6_000


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
    return (
        content[:max_chars]
        + f"\n\n… [truncated for memory; total {len(content):,} chars]"
    )


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
        content[:max_chars]
        + f"\n\n… [truncated for context; total {len(content):,} chars; "
        "re-read file if you need more]"
    )