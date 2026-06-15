"""TUI modal for custom sub-agent types."""

from __future__ import annotations

import asyncio

import pytest
from cli.tui.modals.subagent_types_manager import SubagentTypesManagerScreen


class _Host:
    profile = "default"

    def transcript_write(self, _message: str) -> None:
        pass


@pytest.mark.asyncio
async def test_create_opens_form_without_select_error() -> None:
    from textual.app import App

    app = App()
    async with app.run_test(size=(100, 32)) as pilot:
        await app.push_screen(SubagentTypesManagerScreen(_Host()))
        await pilot.pause()
        screen = app.screen
        assert screen._view == "list"
        await pilot.click("#btn-sat-create")
        await pilot.pause()
        assert screen._view == "form"
        assert screen.query_one("#sat-form").display is True
        assert screen.query_one("#sat-type-list").display is False


@pytest.mark.asyncio
async def test_edit_delete_visible_but_disabled_for_builtin() -> None:
    from textual.app import App

    app = App()
    async with app.run_test(size=(100, 32)) as pilot:
        await app.push_screen(SubagentTypesManagerScreen(_Host()))
        await pilot.pause()
        screen = app.screen
        edit = screen.query_one("#btn-sat-edit")
        delete = screen.query_one("#btn-sat-delete")
        assert edit.display is True
        assert delete.display is True
        assert edit.disabled is True
        assert delete.disabled is True