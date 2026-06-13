"""Multiline input widget."""

from __future__ import annotations

from textual.widgets import TextArea


class HolixInputArea(TextArea):
    """Markdown input for user messages."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "input-area")
        kwargs.setdefault("language", "markdown")
        kwargs.setdefault("theme", "monokai")
        super().__init__(**kwargs)