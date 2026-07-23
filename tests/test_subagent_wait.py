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
from core.subagents import manager as manager_mod
from core.subagents.manager import SubAgentManager


def _manager() -> SubAgentManager:
    parent = MagicMock()
    parent.config = MagicMock(
        enable_subagents=True,
        subagent_max_concurrent=4,
        confirmation_timeout=0,
        subagent_process_timeout=900.0,
    )
    parent.emit = MagicMock()
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


@pytest.mark.asyncio
async def test_wait_for_timeout_does_not_cancel_async_subagent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outer wait_for timeout must not kill a still-running async sub-agent."""
    # Idle sub-agent must not get infinite extensions.
    monkeypatch.setattr(manager_mod, "WAIT_GRACE_S", 0.0)
    monkeypatch.setattr(manager_mod, "WAIT_ACTIVE_IDLE_S", 0.0)
    monkeypatch.setattr(manager_mod, "WAIT_MAX_EXTENSIONS", 0)

    mgr = _manager()
    cfg = SubAgentConfig(name="web_researcher", process_mode=ProcessMode.ASYNC)
    handle = SubAgentHandle(name="web_researcher", config=cfg, status=SubAgentStatus.RUNNING)

    async def slow_runner() -> None:
        await asyncio.sleep(0.15)
        handle.result = SubAgentResult(
            name="web_researcher",
            success=True,
            response="finished after slow work",
            duration_ms=150.0,
        )
        handle.status = SubAgentStatus.COMPLETED
        mgr.notify_handle_finished("web_researcher")

    handle.task = asyncio.create_task(slow_runner())
    mgr._register_handle("web_researcher", handle)

    with pytest.raises(TimeoutError, match="timed out waiting"):
        await mgr.wait_for("web_researcher", timeout=0.05)

    assert handle.task is not None
    await asyncio.wait_for(handle.task, timeout=2.0)
    assert handle.result is not None
    assert handle.result.success is True
    assert handle.result.response == "finished after slow work"


@pytest.mark.asyncio
async def test_wait_for_extends_when_subagent_is_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Active sub-agent should get more wait budget instead of hard timeout."""
    monkeypatch.setattr(manager_mod, "WAIT_GRACE_S", 0.02)
    monkeypatch.setattr(manager_mod, "WAIT_ACTIVE_IDLE_S", 5.0)
    monkeypatch.setattr(manager_mod, "WAIT_MAX_EXTENSIONS", 5)

    mgr = _manager()
    cfg = SubAgentConfig(name="coder-python-1", process_mode=ProcessMode.ASYNC)
    handle = SubAgentHandle(
        name="coder-python-1",
        config=cfg,
        status=SubAgentStatus.RUNNING,
    )
    handle.started_at = asyncio.get_running_loop().time()
    handle.record_activity("step", "Reasoning step 1/10", steps_taken=1)
    mgr._register_handle("coder-python-1", handle)

    async def finish_after_extension() -> None:
        # Longer than the first budget (0.08s), shorter than budget+extension.
        await asyncio.sleep(0.12)
        handle.record_activity("step", "Reasoning step 2/10", steps_taken=2)
        handle.result = SubAgentResult(
            name="coder-python-1",
            success=True,
            response="done after extension",
            duration_ms=120.0,
            steps_taken=2,
        )
        handle.status = SubAgentStatus.COMPLETED
        mgr.notify_handle_finished("coder-python-1")

    asyncio.create_task(finish_after_extension())

    result = await mgr.wait_for("coder-python-1", timeout=0.08)
    assert result.success is True
    assert result.response == "done after extension"
    # At least one extension notice should have been emitted.
    emit = mgr._parent.emit
    assert emit.called
    types = [getattr(c.args[0], "type", None) for c in emit.call_args_list if c.args]
    assert any(str(t) == "subagent_timeout_extended" for t in types)


@pytest.mark.asyncio
async def test_wait_for_accepts_full_job_id() -> None:
    """list_subagents exposes owner::name; wait_for must resolve to local handle."""
    mgr = _manager()
    cfg = SubAgentConfig(name="coder-python", process_mode=ProcessMode.ASYNC)
    handle = SubAgentHandle(
        name="coder-python",
        config=cfg,
        status=SubAgentStatus.RUNNING,
    )
    handle.result = SubAgentResult(
        name="coder-python",
        success=True,
        response="ok",
        duration_ms=5.0,
    )
    handle.status = SubAgentStatus.COMPLETED
    mgr._register_handle("coder-python", handle)

    assert mgr.get_handle("studio-1994594::coder-python") is handle
    result = await mgr.wait_for("studio-1994594::coder-python", timeout=1.0)
    assert result.success is True
    assert result.response == "ok"


@pytest.mark.asyncio
async def test_wait_for_timeout_when_idle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(manager_mod, "WAIT_GRACE_S", 0.0)
    monkeypatch.setattr(manager_mod, "WAIT_ACTIVE_IDLE_S", 0.01)
    monkeypatch.setattr(manager_mod, "WAIT_MAX_EXTENSIONS", 3)

    mgr = _manager()
    cfg = SubAgentConfig(name="stuck", process_mode=ProcessMode.ASYNC)
    handle = SubAgentHandle(name="stuck", config=cfg, status=SubAgentStatus.RUNNING)
    handle.started_at = asyncio.get_running_loop().time() - 10.0
    handle.last_activity_at = handle.started_at
    mgr._register_handle("stuck", handle)

    with pytest.raises(TimeoutError, match="appears idle/hung"):
        await mgr.wait_for("stuck", timeout=0.05)