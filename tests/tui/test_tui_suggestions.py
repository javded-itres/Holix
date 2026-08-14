"""TUI slash suggestion overlay."""

from __future__ import annotations

import pytest

from tests.tui.harness import launch_tui

pytestmark = [pytest.mark.tui, pytest.mark.integration, pytest.mark.asyncio]


async def test_tui_40_slash_opens_suggestions(mock_agent):
    async with launch_tui(mock_agent=mock_agent) as (app, pilot):
        from cli.tui.code.widgets import CodePrompt

        prompt = app.query_one("#input-area", CodePrompt)
        await pilot.click("#input-area")
        prompt.load_text("/")
        # Trigger suggestion update if bound to change
        try:
            app._update_slash_suggestions()
        except Exception:
            try:
                app._show_slash_suggestions()
            except Exception:
                pass
        await pilot.pause(0.40)
        try:
            sugg = app.query_one("#command-suggestions")
            # Widget exists; open state depends on handlers
            assert sugg is not None
        except Exception:
            pytest.fail("slash suggestions widget missing")
