"""Chat history widget."""

from __future__ import annotations

from textual.widgets import RichLog


class HelixChatLog(RichLog):
    """RichLog for agent output with stable id and scroll helpers."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "chat-log")
        kwargs.setdefault("wrap", True)
        kwargs.setdefault("highlight", True)
        kwargs.setdefault("markup", True)
        kwargs.setdefault("max_lines", 600)
        super().__init__(**kwargs)

    def append(self, content) -> None:
        """Append content to the log."""
        try:
            self.write(content)
        except Exception:
            pass

    @staticmethod
    def is_at_bottom(chat_log: RichLog) -> bool:
        """True when scrolled to (or very near) the bottom."""
        try:
            sy = chat_log.scroll_y
            msy = chat_log.max_scroll_y
            if sy is None or msy is None:
                return False
            return sy >= msy - 1
        except Exception:
            return False

    def scroll_to_bottom(self, *, animate: bool = False) -> None:
        try:
            self.scroll_end(animate=animate)
        except Exception:
            pass