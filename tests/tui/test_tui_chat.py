"""TUI chat send path with mock agent.run."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tests.tui.harness import launch_tui, make_mock_agent

pytestmark = [pytest.mark.tui, pytest.mark.integration, pytest.mark.asyncio]


async def test_tui_20_send_message_calls_agent():
    from core.agent_events import FinalResponseEvent

    agent = make_mock_agent(reply="pong-from-agent")

    async def _run(*a, **k):
        agent.events.emit(
            FinalResponseEvent(
                content="pong-from-agent",
                conversation_id=k.get("conversation_id") or "tui",
            )
        )
        return "pong-from-agent"

    agent.run = AsyncMock(side_effect=_run)

    async with launch_tui(mock_agent=agent) as (app, pilot):
        await app.type_and_submit(pilot, "hello holix tui")
        for _ in range(80):
            await pilot.pause(0.40)
            if agent.run.await_count:
                break
        assert agent.run.await_count >= 1, (
            f"agent.run not called; transcript={app.transcript_plain()[-400:]!r}"
        )
        text = app.transcript_plain()
        assert "hello holix tui" in text or "❯" in text


async def test_tui_21_empty_enter_does_not_call_agent(mock_agent):
    async with launch_tui(mock_agent=mock_agent) as (app, pilot):
        await pilot.click("#input-area")
        await pilot.press("enter")
        await pilot.pause(0.40)
        assert mock_agent.run.await_count == 0


async def test_tui_22_slash_does_not_call_agent_run(mock_agent):
    async with launch_tui(mock_agent=mock_agent) as (app, pilot):
        await app.type_and_submit(pilot, "/help")
        await pilot.pause(0.60)
        assert mock_agent.run.await_count == 0
