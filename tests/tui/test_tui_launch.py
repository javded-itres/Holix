"""Full TUI launch: mount, ready state, chrome widgets."""

from __future__ import annotations

import pytest

from tests.tui.harness import launch_tui

pytestmark = [pytest.mark.tui, pytest.mark.integration, pytest.mark.asyncio]


async def test_tui_01_launches_and_shows_ready(mock_agent):
    async with launch_tui(mock_agent=mock_agent) as (app, pilot):
        assert app.title == "Holix"
        assert app._agent_init_state == "ready"
        assert app.agent is not None
        text = app.transcript_plain().lower()
        assert "holix" in text
        assert "ready" in text


async def test_tui_02_prompt_enabled_after_init(mock_agent):
    async with launch_tui(mock_agent=mock_agent) as (app, pilot):
        from cli.tui.code.widgets import CodePrompt

        prompt = app.query_one("#input-area", CodePrompt)
        assert prompt.disabled is False
        await pilot.click("#input-area")
        await pilot.pause(0.40)
        assert app.focused is prompt or prompt.has_focus


async def test_tui_03_core_widgets_present(mock_agent):
    async with launch_tui(mock_agent=mock_agent) as (app, pilot):
        assert app.query_one("#transcript") is not None
        assert app.query_one("#input-area") is not None
        assert app.query_one("#status-bar") is not None
        # process / context bars exist
        assert app.query("#status-bar")
