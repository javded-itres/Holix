"""Read-only full transcript for copy-friendly editing."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual import on
from textual.widgets import Footer, Header, Static, TextArea

from cli.tui.code.widgets.copy_selection_bar import CopySelectionBar
from cli.tui.shared.clipboard import copy_text_best_effort
from cli.tui.shared.copy_bar import VIEWER_COPY_BAR_ID, hide_copy_bar, show_copy_bar
from cli.tui.shared.keyboard_layout import primary_copy_shortcut_label, transcript_viewer_bindings


class TranscriptViewerScreen(ModalScreen[None]):
    """Fullscreen-ish modal with selectable plain transcript."""

    BINDINGS = transcript_viewer_bindings()

    DEFAULT_CSS = """
    TranscriptViewerScreen {
        align: center middle;
    }
    #viewer-panel {
        width: 95%;
        height: 90%;
        border: solid $primary;
        background: $surface;
        padding: 0 1;
    }
    #viewer-hint {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-style: dim;
    }
    #viewer-text {
        height: 1fr;
    }
    """

    def __init__(self, text: str, title: str = "Transcript") -> None:
        super().__init__()
        self._text = text
        self._title = title

    @staticmethod
    def _viewer_hint() -> str:
        return (
            f"Select text → Copy button · {primary_copy_shortcut_label()} · Esc close"
        )

    def compose(self) -> ComposeResult:
        with Vertical(id="viewer-panel"):
            yield Header(show_clock=False)
            yield Static(self._viewer_hint(), id="viewer-hint")
            yield TextArea(self._text, id="viewer-text", read_only=True, show_line_numbers=True)
            yield CopySelectionBar(id=VIEWER_COPY_BAR_ID)
            yield Footer()

    def on_mount(self) -> None:
        self.title = self._title
        try:
            ta = self.query_one("#viewer-text", TextArea)
            ta.focus()
        except Exception:
            pass

    def _copy_from_viewer(self) -> bool:
        try:
            ta = self.query_one("#viewer-text", TextArea)
            text = ta.selected_text.strip() or self._text.strip()
            if not text:
                return False
            return copy_text_best_effort(self.app, text)
        except Exception:
            return False

    def _show_copy_feedback(self, *, ok: bool) -> None:
        try:
            hint = self.query_one("#viewer-hint", Static)
            if ok:
                hint.update("[green]Copied to clipboard[/green]")
                self.set_timer(1.5, lambda: hint.update(self._viewer_hint()))
            else:
                hint.update("[red]Copy failed — try ⌘C in the terminal[/red]")
        except Exception:
            pass

    def action_copy_selection(self) -> None:
        ok = self._copy_from_viewer()
        self._show_copy_feedback(ok=ok)
        hide_copy_bar(self, VIEWER_COPY_BAR_ID)

    @on(TextArea.SelectionChanged, "#viewer-text")
    def _on_viewer_selection_changed(self, event: TextArea.SelectionChanged) -> None:
        if event.text_area.selected_text.strip():
            show_copy_bar(self, VIEWER_COPY_BAR_ID)
        else:
            hide_copy_bar(self, VIEWER_COPY_BAR_ID)

    @on(CopySelectionBar.Pressed, f"#{VIEWER_COPY_BAR_ID}")
    def _on_viewer_copy_pressed(self) -> None:
        self.action_copy_selection()

    def action_dismiss(self) -> None:
        self.dismiss(None)