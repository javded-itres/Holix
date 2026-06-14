"""Human-readable sub-agent tool output for MAX chat."""

from __future__ import annotations

from core.presenters.subagent_tool_text import format_subagent_tool_notice


def format_list_subagents_result(raw: str) -> str:
    """Turn list_subagents JSON into a short MAX-friendly message."""
    return format_subagent_tool_notice("list_subagents", raw)