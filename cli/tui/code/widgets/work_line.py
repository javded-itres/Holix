"""Live line above the prompt: the agent is working, and which tasks are in flight."""

from __future__ import annotations

from textual.widgets import Static

from cli.tui.shared.text_escape import escape_for_markup


class CodeWorkLine(Static):
    """Hidden when the agent is idle and nothing is running in the background."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "work-line")
        super().__init__("", **kwargs)
        self.display = False

    def set_work(self, *, working: str = "", tasks: list[str] | None = None) -> None:
        rows: list[str] = []
        current = (working or "").strip()
        if current:
            rows.append(f"[bold yellow]●[/bold yellow] {escape_for_markup(current)}")
        for task in (tasks or [])[:5]:
            text = (task or "").strip()
            if text:
                rows.append(f"[cyan]◎[/cyan] {escape_for_markup(text)}")
        if not rows:
            self.update("")
            self.display = False
            self.remove_class("visible")
            return
        self.update("\n".join(rows))
        self.display = True
        self.add_class("visible")
