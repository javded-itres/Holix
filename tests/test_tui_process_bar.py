"""TUI top bar lists only live background processes."""

from __future__ import annotations

import pytest
from cli.tui.code.widgets.process_bar import (
    CodeProcessBar,
    ProcessBarRow,
    process_bar_row_markup,
)
from textual.app import App, ComposeResult
from textual.markup import to_content


class _BarApp(App):
    def compose(self) -> ComposeResult:
        yield CodeProcessBar()


@pytest.mark.asyncio
async def test_process_bar_shows_running_and_hides_when_empty() -> None:
    app = _BarApp()
    async with app.run_test() as _pilot:
        bar = app.query_one("#process-bar", CodeProcessBar)
        assert bar.display is False
        bar.set_processes(
            [
                ("proc_a", "uvicorn · pid 1 · :8000"),
                ("proc_b", "worker · pid 2"),
            ]
        )
        assert bar.display is True
        assert bar.process_ids == ["proc_a", "proc_b"]
        assert len(list(bar.children)) == 2
        bar.set_processes([])
        assert bar.display is False
        assert bar.process_ids == []


@pytest.mark.asyncio
async def test_process_bar_set_process_hides_unhealthy() -> None:
    app = _BarApp()
    async with app.run_test() as _pilot:
        bar = app.query_one("#process-bar", CodeProcessBar)
        bar.set_process("uvicorn · pid 1", process_id="proc_a", healthy=True)
        assert bar.display is True
        bar.set_process("uvicorn · pid 1", process_id="proc_a", healthy=False)
        assert bar.display is False


def test_process_bar_row_markup_is_valid() -> None:
    to_content(process_bar_row_markup("uvicorn · pid 1 · :8000"))
    to_content(process_bar_row_markup("api [dev] · pid 2"))


@pytest.mark.asyncio
async def test_process_bar_row_renders_with_brackets_in_label() -> None:
    app = _BarApp()
    async with app.run_test() as _pilot:
        bar = app.query_one("#process-bar", CodeProcessBar)
        bar.set_processes([("proc_a", "uvicorn [dev] · pid 1")])
        row = bar.query_one(ProcessBarRow)
        _ = row.visual
