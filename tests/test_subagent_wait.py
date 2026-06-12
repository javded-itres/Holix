"""Sub-agent spawn/wait result collection."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from core.subagents.base import (
    ProcessMode,
    SubAgentConfig,
    SubAgentHandle,
    SubAgentResult,
    SubAgentStatus,
)
from core.subagents.manager import SubAgentManager


def _manager() -> SubAgentManager:
    parent = MagicMock()
    parent.config = MagicMock(
        enable_subagents=True,
        subagent_max_concurrent=4,
        confirmation_timeout=0,
    )
    return SubAgentManager(parent)


@pytest.mark.asyncio
async def test_wait_for_returns_after_early_notify() -> None:
    """Completion notified before handle registration must not hang wait_for."""
    mgr = _manager()
    cfg = SubAgentConfig(name="researcher", process_mode=ProcessMode.PROCESS)
    handle = SubAgentHandle(
        name="researcher",
        config=cfg,
        status=SubAgentStatus.RUNNING,
    )
    handle.result = SubAgentResult(
        name="researcher",
        success=True,
        response="done",
        duration_ms=10.0,
    )
    handle.status = SubAgentStatus.COMPLETED

    mgr.notify_handle_finished("researcher")
    mgr._register_handle("researcher", handle)

    result = await asyncio.wait_for(mgr.wait_for("researcher", timeout=2.0), timeout=2.0)
    assert result.success is True
    assert result.response == "done"


@pytest.mark.asyncio
async def test_wait_for_process_mode_without_event() -> None:
    """Process-mode wait must observe status even if done_event was never set."""
    mgr = _manager()
    cfg = SubAgentConfig(name="coder", process_mode=ProcessMode.PROCESS)
    handle = SubAgentHandle(
        name="coder",
        config=cfg,
        status=SubAgentStatus.RUNNING,
    )
    mgr._register_handle("coder", handle)

    async def finish_later() -> None:
        await asyncio.sleep(0.05)
        handle.result = SubAgentResult(
            name="coder",
            success=True,
            response="async finish",
            duration_ms=50.0,
        )
        handle.status = SubAgentStatus.COMPLETED

    asyncio.create_task(finish_later())
    result = await asyncio.wait_for(mgr.wait_for("coder", timeout=2.0), timeout=2.0)
    assert result.response == "async finish"


@pytest.mark.asyncio
async def test_async_spawn_wait_returns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr = _manager()
    cfg = SubAgentConfig(name="writer", process_mode=ProcessMode.ASYNC)

    async def fake_run(config: SubAgentConfig, task: str) -> SubAgentHandle:
        handle = SubAgentHandle(
            name=config.name,
            config=config,
            status=SubAgentStatus.RUNNING,
        )

        async def runner() -> None:
            await asyncio.sleep(0.01)
            handle.result = SubAgentResult(
                name=config.name,
                success=True,
                response=f"ok:{task}",
                duration_ms=10.0,
            )
            handle.status = SubAgentStatus.COMPLETED
            mgr.notify_handle_finished(config.name)

        handle.task = asyncio.create_task(runner())
        return handle

    async def _noop_register_async(*_a, **_k) -> None:
        return None

    monkeypatch.setattr(mgr._async_runner, "run", fake_run)
    monkeypatch.setattr(mgr._comm_bus, "register_async", _noop_register_async)

    handle = await mgr.spawn_sub_agent(cfg, "summarize")
    result = await mgr.wait_for(handle.name, timeout=2.0)
    assert result.success is True
    assert result.response == "ok:summarize"