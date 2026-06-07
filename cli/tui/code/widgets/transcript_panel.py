"""Transcript region with overlay Copy button on selection."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.message import Message
from textual.selection import Selection

from cli.tui.code.widgets.transcript import CodeTranscript
from cli.tui.shared.copy_bar import selection_has_text


class TranscriptPanel(Container):
    """RichLog transcript (copy bar lives at screen bottom)."""

    DEFAULT_CSS = """
    TranscriptPanel {
        height: 1fr;
    }
    """

    class SelectionActive(Message):
        """User selected text in the transcript."""

        bubble = True

    class SelectionCleared(Message):
        """Transcript selection cleared."""

        bubble = True

    def compose(self) -> ComposeResult:
        yield CodeTranscript()

    def selection_updated(self, selection: Selection | None) -> None:
        """Bubble selection state from the nested transcript."""
        if selection_has_text(selection):
            self.post_message(self.SelectionActive())
        else:
            self.post_message(self.SelectionCleared())