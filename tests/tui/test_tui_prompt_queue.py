"""TUI prompt queue: enqueue while busy, edit, delete, sequential run."""

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


@pytest.mark.asyncio
async def test_second_prompt_queues_while_agent_runs():
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
        for _ in range(40):
            await pilot.pause(0.05)
            if seen:
                break
        assert seen == ["first task"]

        await app.type_and_submit(pilot, "second task")
        await pilot.pause(0.20)
        queue = app.query_one("#prompt-queue", PromptQueue)
        assert queue.display is True
        assert [i.text for i in queue.items] == ["second task"]
        assert seen == ["first task"]

        gate.set()
        for _ in range(80):
            await pilot.pause(0.05)
            if seen == ["first task", "second task"]:
                break
        assert seen == ["first task", "second task"]
        for _ in range(20):
            await pilot.pause(0.05)
            if not app.query_one("#prompt-queue", PromptQueue).display:
                break
        assert app.query_one("#prompt-queue", PromptQueue).display is False


@pytest.mark.asyncio
async def test_queue_delete_drops_item_without_running_it():
    gate = asyncio.Event()
    seen: list[str] = []
    agent = make_mock_agent()

    async def _run(*, user_input: str = "", **_k):
        seen.append(user_input)
        await gate.wait()
        return "done"

    agent.run = AsyncMock(side_effect=_run)

    async with launch_tui(mock_agent=agent) as (app, pilot):
        await app.type_and_submit(pilot, "keep running")
        for _ in range(40):
            await pilot.pause(0.05)
            if seen:
                break
        await app.type_and_submit(pilot, "drop me")
        await pilot.pause(0.20)
        queue = app.query_one("#prompt-queue", PromptQueue)
        assert queue.items
        item_id = queue.items[0].item_id
        app._remove_queued_prompt(item_id)
        await pilot.pause(0.10)
        assert app.query_one("#prompt-queue", PromptQueue).display is False
        gate.set()
        await pilot.pause(0.40)
        assert seen == ["keep running"]


@pytest.mark.asyncio
async def test_queue_edit_loads_text_into_prompt():
    gate = asyncio.Event()
    agent = make_mock_agent()

    async def _run(*, user_input: str = "", **_k):
        await gate.wait()
        return "done"

    agent.run = AsyncMock(side_effect=_run)

    async with launch_tui(mock_agent=agent) as (app, pilot):
        from cli.tui.code.widgets import CodePrompt

        await app.type_and_submit(pilot, "busy now")
        for _ in range(40):
            await pilot.pause(0.05)
            if agent.run.await_count:
                break
        await app.type_and_submit(pilot, "edit this later")
        await pilot.pause(0.20)
        item_id = app._prompt_queue[0].item_id
        app._edit_queued_prompt(item_id)
        await pilot.pause(0.10)
        prompt = app.query_one("#input-area", CodePrompt)
        assert prompt.text == "edit this later"
        assert app._prompt_queue == []
        gate.set()


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
