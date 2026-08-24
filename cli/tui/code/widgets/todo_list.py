"""Sticky TUI checklist for the current session todos."""

from __future__ import annotations

from core.runtime.todo_list import TODO_ICONS, items_as_dicts
from textual.containers import Vertical
from textual.widgets import Static

from cli.tui.shared.text_escape import escape_for_markup


def todo_row_markup(status: str, content: str) -> str:
    safe = escape_for_markup(content)
    icon = TODO_ICONS.get(status, "☐")
    if status == "in_progress":
        return f"[bold yellow]{icon} {safe}[/bold yellow]"
    if status == "completed":
        return f"[green]{icon} {safe}[/green]"
    if status == "cancelled":
        return f"[dim]{icon} {safe}[/dim]"
    return f"{icon} {safe}"


class CodeTodoList(Vertical):
    """Visible while the session has at least one todo."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "todo-list")
        super().__init__(**kwargs)
        self.display = False
        self._items: list[dict[str, str]] = []

    @property
    def items(self) -> list[dict[str, str]]:
        return list(self._items)

    def set_todos(self, items: object = None) -> None:
        rows = items_as_dicts(items or [])
        self._items = rows
        try:
            self.remove_children()
        except Exception:
            pass
        if not rows:
            self.display = False
            self.remove_class("visible")
            return
        self.mount(Static("[bold]Todos[/bold]", classes="todo-header"))
        for item in rows[:12]:
            self.mount(
                Static(
                    todo_row_markup(item.get("status") or "pending", item.get("content") or ""),
                    classes="todo-row",
                )
            )
        extra = len(rows) - 12
        if extra > 0:
            self.mount(Static(f"[dim]+{extra} more[/dim]", classes="todo-row"))
        self.display = True
        self.add_class("visible")
