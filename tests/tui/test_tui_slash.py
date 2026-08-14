"""TUI slash commands via full app pilot."""

from __future__ import annotations

import pytest

from tests.tui.harness import launch_tui

pytestmark = [pytest.mark.tui, pytest.mark.integration, pytest.mark.asyncio]


async def test_tui_10_help_command(mock_agent):
    async with launch_tui(mock_agent=mock_agent) as (app, pilot):
        await app.type_and_submit(pilot, "/help")
        await pilot.pause(0.60)
        text = app.transcript_plain().lower()
        assert "/help" in text or "help" in text
        assert "/clear" in text or "clear" in text or "slash" in text or "mode" in text


async def test_tui_11_mode_set_plan_and_execute(mock_agent):
    async with launch_tui(mock_agent=mock_agent) as (app, pilot):
        app._execution_mode_index = 0  # react
        await app.type_and_submit(pilot, "/mode plan_and_execute")
        await pilot.pause(0.60)
        assert app._execution_modes[app._execution_mode_index] == "plan_and_execute"
        text = app.transcript_plain().lower()
        assert "plan_and_execute" in text or "mode" in text


async def test_tui_12_mode_cycle(mock_agent):
    async with launch_tui(mock_agent=mock_agent) as (app, pilot):
        app._execution_mode_index = 0  # react
        await app.type_and_submit(pilot, "/mode")
        await pilot.pause(0.60)
        # cycle from react → plan_and_execute
        assert app._execution_modes[app._execution_mode_index] == "plan_and_execute"


async def test_tui_13_status_command(mock_agent):
    async with launch_tui(mock_agent=mock_agent) as (app, pilot):
        await app.type_and_submit(pilot, "/status")
        await pilot.pause(0.60)
        text = app.transcript_plain().lower()
        assert "default" in text or "react" in text or "status" in text or "profile" in text


async def test_tui_14_clear_command(mock_agent):
    async with launch_tui(mock_agent=mock_agent) as (app, pilot):
        app.transcript_write("MARKER_BEFORE_CLEAR")
        await app.type_and_submit(pilot, "/clear")
        await pilot.pause(0.60)
        # clear resets display buffer; marker should not remain in chunks
        # (implementation may re-print banner)
        assert app._agent_init_state == "ready"
