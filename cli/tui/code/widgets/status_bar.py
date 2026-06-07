"""Single-line status footer."""

from textual.widgets import Static


class CodeStatusBar(Static):
    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "status-bar")
        super().__init__("", **kwargs)

    def set_line(self, text: str) -> None:
        self.update(text)