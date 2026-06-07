"""Shared TUI utilities (no eager app imports — avoids circular imports)."""

from cli.tui.shared.formatters import format_tool_args, format_tool_header, truncate_text
from cli.tui.shared.keyboard_layout import (
    code_tui_bindings,
    is_apple_terminal,
    is_iterm,
    is_macos,
    is_slash_command,
    macos_copy_binding_keys,
    normalize_slash_input,
    primary_copy_shortcut_label,
    shortcut_label,
    slash_command_prefix,
    terminal_copy_hint,
    terminal_program,
)
from cli.tui.shared.transcript_store import (
    TranscriptStore,
    plain_from_rich_write,
    strip_rich_markup,
)

__all__ = [
    "TranscriptStore",
    "code_tui_bindings",
    "format_tool_args",
    "format_tool_header",
    "is_apple_terminal",
    "is_iterm",
    "is_macos",
    "is_slash_command",
    "macos_copy_binding_keys",
    "normalize_slash_input",
    "plain_from_rich_write",
    "primary_copy_shortcut_label",
    "shortcut_label",
    "slash_command_prefix",
    "terminal_copy_hint",
    "terminal_program",
    "strip_rich_markup",
    "truncate_text",
]