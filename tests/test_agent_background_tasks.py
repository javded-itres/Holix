"""Same-agent background tasks: start, track, and wake on completion."""

from __future__ import annotations

import asyncio
import sys

import pytest
from core.runtime.agent_tasks import (
    format_agent_task_wakeup,
    get_agent_task_registry,
    register_agent_task_listener,
    started_task_message,
    unregister_agent_task_listener,
)
from core.tools.terminal import TerminalTool


@pytest.fixture(autouse=True)
def _clear_tasks():
    registry = get_agent_task_registry()
    registry.clear()
    yield
    registry.clear()


def _spawn_kw() -> dict:
    kw: dict = {}
    if sys.platform != "win32":
        kw["start_new_session"] = True
    return kw


async def _wait_done(task_id: str, timeout: float = 5.0):
    registry = get_agent_task_registry()
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        task = registry.get(task_id)
        if task is not None and not task.is_running():
            return task
        await asyncio.sleep(0.02)
    raise AssertionError(f"task {task_id} did not finish")


@pytest.mark.asyncio
async def test_background_task_wakes_listener_with_output() -> None:
    seen: list[str] = []

    def _on_task(task) -> None:
        seen.append(task.task_id)

    register_agent_task_listener(_on_task)
    try:
        launched = await get_agent_task_registry().launch_shell(
            command="python3 -c \"print('done-marker')\"",
            description="print marker",
            profile="alice",
            conversation_id="conv-1",
            cwd=None,
            use_shell=False,
            argv=[sys.executable, "-c", "print('done-marker')"],
            spawn_kw=_spawn_kw(),
        )
        assert not isinstance(launched, str)
        assert launched.is_running()
        assert "id=" in started_task_message(launched)
        finished = await _wait_done(launched.task_id)
    finally:
        unregister_agent_task_listener(_on_task)

    assert finished.status == "completed"
    assert finished.exit_code == 0
    assert "done-marker" in finished.output
    assert seen == [finished.task_id]
    text = format_agent_task_wakeup(finished)
    assert "same agent, not a sub-agent" in text
    assert "done-marker" in text
    assert get_agent_task_registry().running_count(profile="alice", conversation_id="conv-1") == 0


@pytest.mark.asyncio
async def test_stop_agent_task() -> None:
    launched = await get_agent_task_registry().launch_shell(
        command="sleep 30",
        description="sleep",
        profile="alice",
        conversation_id="conv-2",
        cwd=None,
        use_shell=False,
        argv=["sleep", "30"],
        spawn_kw=_spawn_kw(),
    )
    assert not isinstance(launched, str)
    message = await get_agent_task_registry().stop(launched.task_id)
    assert launched.task_id in message
    finished = await _wait_done(launched.task_id)
    assert finished.status == "killed"


@pytest.mark.asyncio
async def test_terminal_tool_background_returns_immediately(monkeypatch) -> None:
    from core.tools import terminal as terminal_mod

    from config import settings

    monkeypatch.setattr(settings, "enable_terminal_tool", True)
    monkeypatch.setattr(terminal_mod.settings, "enable_terminal_tool", True)
    monkeypatch.setattr(terminal_mod, "terminal_whitelist_enabled", lambda: False)
    tool = TerminalTool()
    result = await tool.execute(
        command=f"{sys.executable} -c \"import time; time.sleep(0.4); print('later')\"",
        background=True,
        description="slow print",
        timeout=1,
    )
    assert result.startswith("Background task started:")
    task_id = result.split("id=", 1)[1].split(" ", 1)[0]
    listing = get_agent_task_registry().format_list(profile="default", conversation_id="default")
    assert task_id in listing
    finished = await _wait_done(task_id)
    assert "later" in finished.output
    assert finished.status == "completed"
