"""Sticky line at the top of the TUI: the user prompt the agent is working on."""

from __future__ import annotations

from textual.widgets import Static

from cli.tui.shared.text_escape import escape_for_markup

_MAX_CHARS = 280


class CodeActivePrompt(Static):
    """Hidden while the agent is idle."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "active-prompt")
        super().__init__("", **kwargs)
        self.display = False

    def set_prompt(self, text: str) -> None:
        shown = _compact(text)
        if not shown:
            self.update("")
            self.display = False
            self.remove_class("visible")
            return
        self.update(f"[bold cyan]❯[/bold cyan] {escape_for_markup(shown)}")
        self.display = True
        self.add_class("visible")


def _compact(text: str) -> str:
    raw = " ".join((text or "").split())
    if not raw:
        return ""
    if len(raw) <= _MAX_CHARS:
        return raw
    return raw[: _MAX_CHARS - 1].rstrip() + "…"
