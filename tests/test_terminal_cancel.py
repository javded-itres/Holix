"""Cooperative cancel for terminal tool mid-command."""

from __future__ import annotations

import asyncio

import pytest
from core.tools.execution_context import cancel_scope, reset_cancel_scope
from core.tools.terminal import TerminalTool


@pytest.mark.asyncio
async def test_terminal_cancel_kills_long_sleep() -> None:
    tool = TerminalTool()
    ev = asyncio.Event()
    token = cancel_scope(ev)

    async def cancel_soon() -> None:
        await asyncio.sleep(0.3)
        ev.set()

    try:
        task = asyncio.create_task(cancel_soon())
        out = await tool.execute("sleep 30", timeout=10)
        await task
        assert "cancel" in out.lower() or "terminated" in out.lower()
    finally:
        reset_cancel_scope(token)


@pytest.mark.asyncio
async def test_terminal_not_started_when_already_cancelled() -> None:
    tool = TerminalTool()
    ev = asyncio.Event()
    ev.set()
    token = cancel_scope(ev)
    try:
        out = await tool.execute("echo hi", timeout=5)
        assert "not started" in out.lower() or "cancel" in out.lower()
    finally:
        reset_cancel_scope(token)
