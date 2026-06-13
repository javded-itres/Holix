"""Main chat column: log, scroll indicator, suggestions, input."""

from __future__ import annotations

from cli.tui.legacy.widgets.chat_log import HolixChatLog
from cli.tui.legacy.widgets.input_area import HolixInputArea
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, ListView, Static


class HolixMainContent(Vertical):
    """Chat log, context bar, and input."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "main-content")
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield HolixChatLog()
        yield Button(
            "↓ New messages below — click or Ctrl+End",
            id="scroll-indicator",
            classes="scroll-indicator",
        )
        yield ListView(id="command-suggestions", classes="command-suggestions")
        yield Static("", id="context-bar")
        yield HolixInputArea()