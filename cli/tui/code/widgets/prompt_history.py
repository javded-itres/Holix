"""Recent user prompt picker above the input."""

from __future__ import annotations

from textual.widgets import ListItem, ListView, Static


def format_history_label(text: str, *, max_len: int = 96) -> str:
    one_line = " ".join((text or "").split())
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 1] + "…"


class PromptHistorySuggestions(ListView):
    """Dropdown of recent user prompts."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "prompt-history")
        kwargs.setdefault("classes", "prompt-history")
        super().__init__(**kwargs)
        self._entries: list[str] = []

    @property
    def entries(self) -> list[str]:
        return self._entries

    def set_entries(self, entries: list[str]) -> None:
        self._entries = list(entries)
        self.clear()
        for text in entries:
            label = format_history_label(text)
            self.append(ListItem(Static(f"[dim]❯[/dim] {label}")))

    def show_dropdown(self) -> None:
        self.add_class("-visible")

    def hide_dropdown(self) -> None:
        self.remove_class("-visible")
        self.clear()
        self._entries = []

    @property
    def is_open(self) -> bool:
        return self.has_class("-visible")