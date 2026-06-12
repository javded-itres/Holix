"""macOS / non-US keyboard layout helpers for Holix TUI."""

from __future__ import annotations

import os

from textual.binding import Binding

from cli.shared.slash_input import (
    is_macos,
)
from cli.shared.slash_input import (
    is_slash_command as is_slash_command,
)
from cli.shared.slash_input import (
    normalize_slash_input as normalize_slash_input,
)
from cli.shared.slash_input import (
    slash_command_prefix as slash_command_prefix,
)


def terminal_program() -> str:
    """TERM_PROGRAM or LC_TERMINAL (iTerm2 sets both)."""
    return os.environ.get("TERM_PROGRAM", "") or os.environ.get("LC_TERMINAL", "")


def is_apple_terminal() -> bool:
    """macOS built-in Terminal.app — does not forward ⌘C to apps."""
    return os.environ.get("TERM_PROGRAM", "") == "Apple_Terminal"


def is_iterm() -> bool:
    return (
        os.environ.get("TERM_PROGRAM", "") == "iTerm.app"
        or os.environ.get("LC_TERMINAL", "") == "iTerm2"
    )


def macos_copy_binding_keys() -> str:
    """Key list for copy_output; Apple Terminal needs ctrl+c (⌘C stays in Terminal)."""
    keys = ["ctrl+shift+c", "super+c", "meta+c"]
    if is_apple_terminal():
        keys.insert(0, "ctrl+c")
    return ",".join(keys)


def primary_copy_shortcut_label() -> str:
    """Primary copy shortcut label for help / startup hints."""
    if not is_macos():
        return shortcut_label("ctrl+shift+c")
    if is_apple_terminal():
        return shortcut_label("ctrl+c")
    return shortcut_label("super+c")


def terminal_copy_hint() -> str | None:
    """One-line hint for copy workflow (F2 viewer vs selection in chat)."""
    label = primary_copy_shortcut_label()
    if is_macos():
        return f"Копирование: F2 /open — в окне {label}; в чате — выделение + Copy"
    return f"Copy: F2 /open — {label} works in the copy window only"


def transcript_viewer_bindings() -> list[Binding]:
    """Copy shortcuts for the F2 transcript modal only."""
    copy_keys = macos_copy_binding_keys() if is_macos() else "ctrl+shift+c"
    return [
        Binding("escape", "dismiss", "Close"),
        Binding("ctrl+w", "dismiss", "Close", show=False),
        Binding(
            copy_keys,
            "copy_selection",
            "Copy",
            show=True,
            priority=True,
            id="viewer_copy",
        ),
    ]


def shortcut_label(key: str) -> str:
    """Human-readable shortcut (⌃ on macOS, Ctrl elsewhere)."""
    if not is_macos():
        return key.replace("+", "+").replace("ctrl", "Ctrl")
    parts = key.split("+")
    out: list[str] = []
    for p in parts:
        low = p.lower()
        if low == "ctrl":
            out.append("⌃")
        elif low == "shift":
            out.append("⇧")
        elif low == "alt" or low == "meta":
            out.append("⌥")
        elif low == "cmd" or low == "command":
            out.append("⌘")
        elif p.startswith("f") and p[1:].isdigit():
            out.append(p.upper())
        else:
            out.append(p.upper() if len(p) == 1 else p)
    return "".join(out)


def code_tui_bindings() -> list[Binding]:
    """Default Holix code TUI bindings; extra scroll keys on macOS."""
    # macOS: quit on ctrl+q; copy shortcuts only in F2 transcript viewer
    if is_macos():
        quit_binding = Binding("ctrl+q", "quit", "Quit", show=True, id="quit")
    else:
        quit_binding = Binding("ctrl+c", "quit", "Quit", show=True, id="quit")

    bindings: list[Binding] = [
        quit_binding,
        Binding("ctrl+l", "clear_chat", "Clear", show=True, id="clear_chat"),
        Binding("enter", "send_message", "Send", priority=True, id="send_message"),
        Binding("ctrl+end", "scroll_bottom", "Bottom", show=True, id="scroll_bottom"),
        Binding("f1", "help", "Help", show=True, id="help"),
        Binding("f2", "open_transcript", "Copy view", show=True, id="open_transcript"),
        Binding("shift+tab", "cycle_execution_mode", "Mode", show=True, id="cycle_mode"),
        Binding("ctrl+s", "stop_all", "Stop", show=True, id="stop_all"),
    ]
    if is_macos():
        bindings.extend(
            [
                Binding("ctrl+up", "scroll_up", "Up", show=True, id="scroll_up"),
                Binding("ctrl+down", "scroll_down", "Down", show=True, id="scroll_down"),
                Binding("ctrl+pageup", "scroll_page_up", "PgUp", show=True, id="scroll_page_up"),
                Binding("ctrl+pagedown", "scroll_page_down", "PgDn", show=True, id="scroll_page_down"),
                Binding("ctrl+home", "scroll_top", "Top", show=True, id="scroll_top"),
                Binding("ctrl+u", "scroll_half_up", show=False, id="scroll_half_up"),
                Binding("ctrl+d", "scroll_half_down", show=False, id="scroll_half_down"),
            ]
        )
    return bindings