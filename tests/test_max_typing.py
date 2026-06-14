"""MAX typing indicator."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from integrations.max.client import MaxClient
from integrations.max.typing_indicator import TypingIndicator


@pytest.mark.asyncio
async def test_send_chat_action_posts_typing_on() -> None:
    seen: list[tuple[str, dict]] = []

    async def handler(request: web.Request) -> web.Response:
        body = await request.json()
        seen.append((request.path, body))
        return web.json_response({"success": True})

    from tests.test_max_client import _start_mock_server

    runner, base = await _start_mock_server(handler)
    try:
        async with MaxClient("tok", base_url=base) as client:
            await client.send_chat_action(201888907, action="typing_on")
        assert seen == [("/chats/201888907/actions", {"action": "typing_on"})]
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_typing_indicator_sends_periodically() -> None:
    calls: list[int] = []
    client = AsyncMock()
    client.send_chat_action = AsyncMock(side_effect=lambda chat_id, **_: calls.append(chat_id))

    indicator = TypingIndicator(client, 42, interval_s=0.05)
    async with indicator:
        await asyncio.sleep(0.15)
    assert calls.count(42) >= 2


@pytest.mark.asyncio
async def test_typing_indicator_noop_without_chat_id() -> None:
    client = AsyncMock()
    client.send_chat_action = AsyncMock()

    indicator = TypingIndicator(client, None, interval_s=0.02)
    async with indicator:
        await asyncio.sleep(0.05)
    client.send_chat_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_typing_indicator_stops_after_context() -> None:
    calls: list[int] = []
    client = AsyncMock()
    client.send_chat_action = AsyncMock(side_effect=lambda chat_id, **_: calls.append(chat_id))

    indicator = TypingIndicator(client, 1, interval_s=0.02)
    async with indicator:
        await asyncio.sleep(0.03)
    before = len(calls)
    await asyncio.sleep(0.08)
    assert len(calls) == before