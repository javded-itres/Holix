"""TUI sticky todo panel."""

from __future__ import annotations

import pytest
from cli.tui.code.widgets.todo_list import CodeTodoList, todo_row_markup
from textual.app import App, ComposeResult
from textual.markup import to_content


class _TodoApp(App):
    def compose(self) -> ComposeResult:
        yield CodeTodoList()


def test_todo_row_markup_is_valid() -> None:
    to_content(todo_row_markup("in_progress", "Write API [dev]"))
    to_content(todo_row_markup("completed", "done"))
    to_content(todo_row_markup("pending", "later"))


@pytest.mark.asyncio
async def test_todo_list_shows_and_hides() -> None:
    app = _TodoApp()
    async with app.run_test() as _pilot:
        bar = app.query_one("#todo-list", CodeTodoList)
        assert bar.display is False
        bar.set_todos(
            [
                {"id": "1", "content": "Write API", "status": "in_progress"},
                {"id": "2", "content": "Tests", "status": "pending"},
            ]
        )
        assert bar.display is True
        assert len(bar.items) == 2
        _ = list(bar.query(".todo-row"))[0].visual
        bar.set_todos([])
        assert bar.display is False
