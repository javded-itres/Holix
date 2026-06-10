"""Sub-agent manager: unique names, concurrency, spawn helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from core.subagents.base import ProcessMode, SubAgentConfig, SubAgentHandle, SubAgentStatus
from core.subagents.manager import SubAgentManager


def _manager(max_concurrent: int = 4) -> SubAgentManager:
    parent = MagicMock()
    parent.config = MagicMock(
        enable_subagents=True,
        subagent_max_concurrent=max_concurrent,
        subagent_process_timeout=60.0,
        subagent_default_process_mode="async",
    )
    return SubAgentManager(parent)


def test_allocate_name_suffix_when_busy() -> None:
    mgr = _manager()
    mgr._handles["researcher"] = SubAgentHandle(
        name="researcher",
        config=SubAgentConfig(name="researcher"),
        status=SubAgentStatus.RUNNING,
    )
    assert mgr.allocate_name("researcher") == "researcher-2"


def test_allocate_name_reuses_slot_when_done() -> None:
    mgr = _manager()
    mgr._handles["coder"] = SubAgentHandle(
        name="coder",
        config=SubAgentConfig(name="coder"),
        status=SubAgentStatus.COMPLETED,
    )
    assert mgr.allocate_name("coder") == "coder"


@pytest.mark.asyncio
async def test_max_concurrent_blocks_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr = _manager(max_concurrent=1)
    mgr._handles["a"] = SubAgentHandle(
        name="a",
        config=SubAgentConfig(name="a"),
        status=SubAgentStatus.RUNNING,
    )

    cfg = SubAgentConfig(name="b", process_mode=ProcessMode.ASYNC)

    async def fake_run(*_a, **_k):
        return SubAgentHandle(name="b", status=SubAgentStatus.RUNNING)

    monkeypatch.setattr(mgr._async_runner, "run", fake_run)
    monkeypatch.setattr(mgr._comm_bus, "register_async", lambda *_: None)

    with pytest.raises(RuntimeError, match="limit"):
        await mgr.spawn_sub_agent(cfg, "task")


def test_format_status_text_lists_jobs() -> None:
    mgr = _manager()
    mgr._handles["researcher-2"] = SubAgentHandle(
        name="researcher-2",
        status=SubAgentStatus.RUNNING,
        task_preview="find docs",
        config=SubAgentConfig(name="researcher-2", process_mode=ProcessMode.PROCESS),
        process_id=12345,
    )
    text = mgr.format_status_text()
    assert "researcher-2" in text
    assert "find docs" in text