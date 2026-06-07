"""Slash command dropdown above the prompt."""

from __future__ import annotations

from textual.widgets import ListItem, ListView, Static

from cli.tui.shared.slash_suggestions import SlashCommandMatch


class SlashCommandSuggestions(ListView):
    """Dropdown list of /commands; visibility toggled via CSS class `-visible`."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "command-suggestions")
        kwargs.setdefault("classes", "command-suggestions")
        super().__init__(**kwargs)
        self._matches: list[SlashCommandMatch] = []

    @property
    def matches(self) -> list[SlashCommandMatch]:
        return self._matches

    def set_matches(self, matches: list[SlashCommandMatch]) -> None:
        self._matches = matches
        self.clear()
        for cmd, desc in matches:
            label = f"[bold cyan]{cmd}[/bold cyan]  [dim]{desc}[/dim]"
            self.append(ListItem(Static(label)))

    def show_dropdown(self) -> None:
        self.add_class("-visible")

    def hide_dropdown(self) -> None:
        self.remove_class("-visible")
        self.clear()
        self._matches = []

    @property
    def is_open(self) -> bool:
        return self.has_class("-visible")