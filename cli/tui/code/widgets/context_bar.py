"""Context window usage bar (token progress)."""

from __future__ import annotations

from typing import Any

from textual.widgets import Static


class CodeContextBar(Static):
    """Unicode block progress bar for context/token usage."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "context-bar")
        super().__init__("[dim]Context: ──[/dim]", **kwargs)

    def set_placeholder(self) -> None:
        self.update("[dim]Context: ──[/dim]")

    def set_usage(self, percent: float, color: str, usage: dict[str, Any]) -> None:
        from core.context.token_counter import TokenCounter

        used_str = TokenCounter.format_token_count(usage["used"])
        total_str = TokenCounter.format_token_count(usage["total"])

        bar_width = 10
        filled = min(bar_width, int(percent / 100 * bar_width))
        empty = bar_width - filled
        filled_bar = "█" * filled
        empty_bar = "░" * empty
        bar_text = f"[{color}]▌{filled_bar}{empty_bar}▐[/{color}]"
        percent_text = f"[{color}]{percent:.0f}%[/{color}]"
        count_text = f"[dim]{used_str}/{total_str}[/dim]"
        self.update(f"Context: {bar_text} {percent_text} {count_text}")