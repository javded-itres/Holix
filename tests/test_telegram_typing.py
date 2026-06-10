"""Telegram typing indicator."""

from __future__ import annotations

import asyncio

import pytest
from integrations.telegram.typing_indicator import TypingIndicator


@pytest.mark.asyncio
async def test_typing_indicator_sends_periodically() -> None:
    calls: list[int] = []

    class FakeBot:
        async def send_chat_action(self, chat_id: int, action: str) -> None:
            calls.append(chat_id)

    bot = FakeBot()
    indicator = TypingIndicator(bot, 42, interval_s=0.05)
    async with indicator:
        await asyncio.sleep(0.15)
    assert calls.count(42) >= 2


@pytest.mark.asyncio
async def test_typing_indicator_stops_after_context() -> None:
    calls: list[int] = []

    class FakeBot:
        async def send_chat_action(self, chat_id: int, action: str) -> None:
            calls.append(chat_id)

    indicator = TypingIndicator(FakeBot(), 1, interval_s=0.02)
    async with indicator:
        await asyncio.sleep(0.03)
    before = len(calls)
    await asyncio.sleep(0.08)
    assert len(calls) == before