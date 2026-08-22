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
        profile_name="default",
    )
    return SubAgentManager(parent)


def test_allocate_name_suffix_when_busy() -> None:
    mgr = _manager()
    mgr._handles["researcher"] = SubAgentHandle(
        name="researcher",
        config=SubAgentConfig(name="researcher"),
        status=SubAgentStatus.RUNNING,
    )
    assert mgr.allocate_name("researcher") == "researcher-1"


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
    assert "profile default" in text


def test_format_status_text_includes_profile_registry_jobs(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI / /subagents must see jobs published by other hosts on this profile."""
    from core.subagents import runtime_registry as rr
    from core.subagents.manager import format_jobs_status_text

    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setattr(
        rr,
        "profile_dir_for_name",
        lambda name, default="default": tmp_path / "profiles" / (name or default),
    )
    owner = rr.owner_key(source="telegram", pid=999)
    handle = SubAgentHandle(
        name="coder",
        status=SubAgentStatus.RUNNING,
        task_preview="fix gateway",
        agent_type="coder",
        config=SubAgentConfig(name="coder", process_mode=ProcessMode.ASYNC),
    )
    rr.publish_handle("admin", handle, owner=owner, source="telegram")

    mgr = _manager()
    mgr._parent.config.profile_name = "admin"
    text = mgr.format_status_text()
    assert "coder" in text
    assert "fix gateway" in text
    assert "telegram" in text
    assert "profile admin" in text

    jobs = rr.list_jobs("admin", include_done=True)
    cli_text = format_jobs_status_text(jobs, profile="admin")
    assert "coder" in cli_text
    assert "telegram" in cli_text
