"""TUI prompt queue: steer a busy turn, then edit or delete what is still queued."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from cli.tui.code.widgets.prompt_queue import PromptQueue, format_queue_label

from tests.tui.harness import launch_tui, make_mock_agent

pytestmark = [pytest.mark.tui, pytest.mark.integration]


def test_format_queue_label_collapses_whitespace() -> None:
    assert format_queue_label("hello   world") == "hello world"
    long = "x" * 120
    assert format_queue_label(long).endswith("…")
    assert len(format_queue_label(long)) == 88


async def _wait_until(pilot, predicate, *, rounds: int = 40) -> None:
    for _ in range(rounds):
        if predicate():
            return
        await pilot.pause(0.05)


@pytest.mark.asyncio
async def test_second_prompt_steers_then_runs_when_unread():
    gate = asyncio.Event()
    seen: list[str] = []

    agent = make_mock_agent()

    async def _run(*, user_input: str = "", **_k):
        seen.append(user_input)
        await gate.wait()
        return "done"

    agent.run = AsyncMock(side_effect=_run)

    async with launch_tui(mock_agent=agent) as (app, pilot):
        await app.type_and_submit(pilot, "first task")
        await _wait_until(pilot, lambda: seen == ["first task"])
        assert seen == ["first task"]

        await app.type_and_submit(pilot, "second task")
        await pilot.pause(0.20)
        queue = app.query_one("#prompt-queue", PromptQueue)
        assert queue.display is False
        assert seen == ["first task"]
        assert "steering the current turn" in app.transcript_plain()

        gate.set()
        await _wait_until(pilot, lambda: seen == ["first task", "second task"], rounds=80)
        assert seen == ["first task", "second task"]
        await _wait_until(
            pilot,
            lambda: app.query_one("#prompt-queue", PromptQueue).display is False,
            rounds=20,
        )
        assert app.query_one("#prompt-queue", PromptQueue).display is False


@pytest.mark.asyncio
async def test_queue_delete_drops_item_without_running_it():
    first_gate = asyncio.Event()
    later_gate = asyncio.Event()
    seen: list[str] = []
    agent = make_mock_agent()

    async def _run(*, user_input: str = "", **_k):
        seen.append(user_input)
        await (first_gate if len(seen) == 1 else later_gate).wait()
        return "done"

    agent.run = AsyncMock(side_effect=_run)

    async with launch_tui(mock_agent=agent) as (app, pilot):
        await app.type_and_submit(pilot, "keep running")
        await _wait_until(pilot, lambda: seen == ["keep running"])
        await app.type_and_submit(pilot, "run next")
        await app.type_and_submit(pilot, "drop me")
        first_gate.set()
        await _wait_until(pilot, lambda: seen == ["keep running", "run next"])
        queue = app.query_one("#prompt-queue", PromptQueue)
        assert [item.text for item in queue.items] == ["drop me"]
        app._remove_queued_prompt(queue.items[0].item_id)
        await pilot.pause(0.10)
        assert app.query_one("#prompt-queue", PromptQueue).display is False
        later_gate.set()
        await pilot.pause(0.40)
        assert seen == ["keep running", "run next"]


@pytest.mark.asyncio
async def test_queue_edit_loads_text_into_prompt():
    first_gate = asyncio.Event()
    later_gate = asyncio.Event()
    seen: list[str] = []
    agent = make_mock_agent()

    async def _run(*, user_input: str = "", **_k):
        seen.append(user_input)
        await (first_gate if len(seen) == 1 else later_gate).wait()
        return "done"

    agent.run = AsyncMock(side_effect=_run)

    async with launch_tui(mock_agent=agent) as (app, pilot):
        from cli.tui.code.widgets import CodePrompt

        await app.type_and_submit(pilot, "busy now")
        await _wait_until(pilot, lambda: bool(agent.run.await_count))
        await app.type_and_submit(pilot, "leave running")
        await app.type_and_submit(pilot, "edit this later")
        first_gate.set()
        await _wait_until(pilot, lambda: seen == ["busy now", "leave running"])
        item_id = app._prompt_queue[0].item_id
        app._edit_queued_prompt(item_id)
        await pilot.pause(0.10)
        prompt = app.query_one("#input-area", CodePrompt)
        assert prompt.text == "edit this later"
        assert app._prompt_queue == []
        later_gate.set()


@pytest.mark.asyncio
async def test_slash_is_not_queued_while_busy():
    gate = asyncio.Event()
    agent = make_mock_agent()

    async def _run(*, user_input: str = "", **_k):
        await gate.wait()
        return "done"

    agent.run = AsyncMock(side_effect=_run)

    async with launch_tui(mock_agent=agent) as (app, pilot):
        await app.type_and_submit(pilot, "agent work")
        for _ in range(40):
            await pilot.pause(0.05)
            if agent.run.await_count:
                break
        await app.type_and_submit(pilot, "/help")
        await pilot.pause(0.30)
        assert app._prompt_queue == []
        text = app.transcript_plain()
        assert "/help" in text
        gate.set()
