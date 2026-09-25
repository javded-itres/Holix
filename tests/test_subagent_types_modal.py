"""TUI modal for custom sub-agent types and built-in overrides."""

from __future__ import annotations

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
async def test_edit_and_delete_enabled_for_builtin() -> None:
    """Built-ins open the same editor; Delete becomes Reset (they live in code)."""
    from core.i18n import t
    from textual.app import App

    app = App()
    async with app.run_test(size=(100, 32)) as pilot:
        await app.push_screen(SubagentTypesManagerScreen(_Host()))
        await pilot.pause()
        screen = app.screen
        assert screen._selected_name  # first row (a built-in) is auto-selected
        edit = screen.query_one("#btn-sat-edit")
        delete = screen.query_one("#btn-sat-delete")
        assert edit.display is True
        assert delete.display is True
        assert edit.disabled is False
        assert delete.disabled is False
        assert str(delete.label) == t("tui.subagent_types.reset", screen._lang)


@pytest.mark.asyncio
async def test_builtin_edit_opens_form_prefilled() -> None:
    from textual.app import App
    from textual.widgets import Input, SelectionList

    app = App()
    async with app.run_test(size=(100, 40)) as pilot:
        await app.push_screen(SubagentTypesManagerScreen(_Host()))
        await pilot.pause()
        screen = app.screen
        name = screen._selected_name
        await pilot.click("#btn-sat-edit")
        await pilot.pause()
        assert screen._view == "form"
        assert screen.query_one("#sat-name", Input).value == name
        assert screen.query_one("#sat-name", Input).disabled is True
        assert screen.query_one("#sat-desc", Input).value  # built-in description
        assert screen.query_one("#sat-prompt").text  # built-in system prompt
        tools_selected = [str(v) for v in screen.query_one("#sat-tools", SelectionList).selected]
        assert "read_file" in tools_selected


@pytest.mark.asyncio
async def test_builtin_save_writes_overlay_not_types() -> None:
    from core.subagents.registry import get_subagent_config
    from core.subagents.store import SubAgentOverlayStore, SubAgentTypeStore
    from textual.app import App
    from textual.widgets import Input

    app = App()
    async with app.run_test(size=(100, 40)) as pilot:
        await app.push_screen(SubagentTypesManagerScreen(_Host()))
        await pilot.pause()
        screen = app.screen
        name = screen._selected_name  # "researcher" (first built-in)
        await pilot.click("#btn-sat-edit")
        await pilot.pause()
        screen.query_one("#sat-desc", Input).value = "Custom researcher description"
        await pilot.click("#btn-sat-save")
        await pilot.pause()
        assert screen._view == "list"

    overlay = SubAgentOverlayStore("default").get(name)
    assert overlay is not None
    assert overlay.description == "Custom researcher description"
    # Built-ins must never land in types.json (that file is for custom types only).
    assert SubAgentTypeStore("default").get(name) is None
    cfg = get_subagent_config(name, profile="default")
    assert cfg.description == "Custom researcher description"


@pytest.mark.asyncio
async def test_builtin_delete_resets_overlay() -> None:
    from core.subagents.store import SubAgentOverlayStore
    from textual.app import App

    SubAgentOverlayStore("default").merge("researcher", description="to be reset")

    app = App()
    async with app.run_test(size=(100, 40)) as pilot:
        await app.push_screen(SubagentTypesManagerScreen(_Host()))
        await pilot.pause()
        screen = app.screen
        assert screen._selected_name == "researcher"
        await pilot.click("#btn-sat-delete")
        await pilot.pause()

    assert SubAgentOverlayStore("default").get("researcher") is None
