"""Limits for tool output stored in conversation memory."""

from __future__ import annotations

DEFAULT_TOOL_MEMORY_MAX_CHARS = 16_384


def truncate_tool_content_for_memory(
    content: str,
    *,
    max_chars: int = DEFAULT_TOOL_MEMORY_MAX_CHARS,
) -> str:
    """Truncate oversized tool output before persisting to SQLite/ChromaDB."""
    if not content or len(content) <= max_chars:
        return content
    return (
        content[:max_chars]
        + f"\n\n… [truncated for memory; total {len(content):,} chars]"
    )