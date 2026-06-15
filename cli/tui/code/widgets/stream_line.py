"""Live assistant stream (updated in place, not appended to RichLog)."""

from __future__ import annotations

from textual.widgets import Static

_STREAM_DISPLAY_MAX = 4000


class CodeStreamLine(Static):
    """Shows in-progress streamed assistant text below the transcript."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "stream-line")
        super().__init__("", **kwargs)
        self.display = False

    def show_text(self, text: str) -> None:
        body = text or ""
        if not body.strip():
            self.update("")
            self.display = False
            return
        if len(body) > _STREAM_DISPLAY_MAX:
            body = "…" + body[-_STREAM_DISPLAY_MAX:]
        self.update(body)
        self.display = True