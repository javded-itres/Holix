"""Multiline prompt input."""

from textual.widgets import TextArea


class CodePrompt(TextArea):
    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "input-area")
        kwargs.setdefault("show_line_numbers", False)
        kwargs.setdefault("soft_wrap", True)
        super().__init__(**kwargs)