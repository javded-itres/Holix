"""Scrollable transcript (RichLog)."""

from __future__ import annotations

from textual.selection import Selection
from textual.widgets import RichLog

from cli.tui.shared.copy_bar import selection_has_text


class CodeTranscript(RichLog):
    """Main conversation log."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "transcript")
        kwargs.setdefault("markup", True)
        kwargs.setdefault("wrap", True)
        kwargs.setdefault("highlight", False)
        super().__init__(**kwargs)

    def selection_updated(self, selection: Selection | None) -> None:
        super().selection_updated(selection)
        panel = self.parent
        if panel is not None and hasattr(panel, "selection_updated"):
            panel.selection_updated(selection)