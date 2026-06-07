"""Escape dynamic text for Textual / Rich markup widgets."""

from __future__ import annotations

from rich.markup import escape as rich_escape


def escape_for_markup(text: str) -> str:
    """Escape ``[`` ``]`` so user/tool content is safe inside markup strings."""
    return rich_escape(text or "")


def format_confirmation_body(tool_name: str, reason: str) -> str:
    """Build confirmation body label with styled tool name."""
    return (
        f"Tool: [bold]{escape_for_markup(tool_name)}[/bold]\n"
        f"Reason: {escape_for_markup(reason)}"
    )