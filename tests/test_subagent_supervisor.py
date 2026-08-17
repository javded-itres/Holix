"""Tests for runtime Subagent Supervisor (detect + guidance)."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.subagents.base import SubAgentConfig, SubAgentHandle, SubAgentStatus
from core.subagents.supervisor import (
    SubagentSupervisor,
    SupervisorPolicy,
    assess_handle,
    build_loop_guidance,
    format_guidance_system_message,
)


def _running_handle(name: str = "coder-1") -> SubAgentHandle:
    h = SubAgentHandle(
        name=name,
        config=SubAgentConfig(name=name, max_steps=50),
        status=SubAgentStatus.RUNNING,
        started_at=time.monotonic(),
        max_steps=50,
    )
    h.touch_activity()
    return h


def test_assess_ok_when_fresh_activity() -> None:
    h = _running_handle()
    h.record_activity("tool_start", "Calling read_file", tool_name="read_file", details="a.py")
    h.record_activity(
        "tool_result",
        "read_file finished",
        tool_name="read_file",
        details="OK: file contents successfully loaded here for analysis",
    )
    d = assess_handle(h, policy=SupervisorPolicy(idle_s=90, min_steps_before_stall=10))
    assert d.kind == "ok"
    assert not d.needs_intervention


def test_assess_green_pytest_asks_for_final_answer() -> None:
    h = _running_handle()
    h.last_tool = "terminal"
    for _ in range(2):
        h.record_activity(
            "tool_start",
            "Calling terminal",
            tool_name="terminal",
            details='{"command": "python -m pytest -q"}',
        )
        h.record_activity(
            "tool_result",
            "terminal finished",
            tool_name="terminal",
            details="Success (exit code 0):\n........\n8 passed in 0.37s",
        )
    d = assess_handle(h)
    assert d.kind == "tests_green"
    assert d.needs_intervention
    assert "final answer" in d.guidance.lower()
    assert "NO tool calls" in d.guidance


def test_assess_terminal_project_launch_guides_to_background_tool() -> None:
    h = _running_handle()
    h.last_tool = "terminal"
    h.record_activity(
        "tool_start",
        "Calling terminal",
        tool_name="terminal",
        details=(
            '{"command": "cd projects/data_address && python -m data_address.main &\\n'
            'sleep 2\\ncurl -s http://127.0.0.1:8000/health"}'
        ),
    )
    h.record_activity(
        "tool_result",
        "terminal finished",
        tool_name="terminal",
        details="Error: Command timed out after 15 seconds",
    )
    h.config.tools = [
        "terminal",
        "start_background_process",
        "check_background_process",
    ]
    d = assess_handle(h)
    assert d.kind == "launch"
    assert d.needs_intervention
    assert "start_background_process" in d.guidance


def test_assess_similar_grep_same_path_is_loop_guidance() -> None:
    h = _running_handle()
    for i, pat in enumerate(
        (
            "Provider",
            "Provider|AsyncContainer",
            "def build_container|Provider",
            "def build_container|return make_async_container",
        )
    ):
        h.record_activity(
            "tool_start",
            "Calling grep",
            tool_name="grep",
            details=f'{{"pattern": "{pat}", "path": "projects/app/di.py"}}',
        )
        h.record_activity(
            "tool_result",
            "grep finished",
            tool_name="grep",
            details="3 match(es) in 1 file(s)",
        )
        h.steps_taken = i + 1
    d = assess_handle(h)
    assert d.kind == "loop"
    assert d.signals.get("search_loop") is True
    assert d.signals.get("path_loop") is True
    assert "read_file" in d.guidance


def test_assess_noop_write_loop_even_when_paths_alternate() -> None:
    h = _running_handle()
    h.last_tool = "write_file"
    h.config.tools = ["read_file", "write_file", "terminal"]
    for path in ("app/ioc.py", "app/application/use_cases.py", "app/ioc.py"):
        h.record_activity(
            "tool_start",
            "Calling write_file",
            tool_name="write_file",
            details=f'{{"path": "{path}"}}',
        )
        h.record_activity(
            "tool_result",
            "write_file finished",
            tool_name="write_file",
            details=f"Updated {path} (no content changes)\n\nSTOP: already exact",
        )
    d = assess_handle(h)
    assert d.kind == "loop"
    assert d.signals.get("noop_write_loop") is True
    assert "final answer" in d.guidance.lower() or "STOP" in d.guidance


def test_assess_loop() -> None:
    h = _running_handle()
    for _ in range(3):
        h.record_activity(
            "tool_start",
            "Calling read_file",
            tool_name="read_file",
            details='{"path":"same.py"}',
        )
        h.record_activity(
            "tool_result",
            "read_file finished",
            tool_name="read_file",
            details="same content again",
        )
    d = assess_handle(h)
    assert d.kind == "loop"
    assert d.needs_intervention
    assert "GUIDANCE" in d.guidance
    assert "What to fix" in d.guidance


def test_assess_thrash() -> None:
    h = _running_handle()
    for i, tool in enumerate(["run_terminal_command", "read_file", "write_file"]):
        h.record_activity("tool_start", f"Calling {tool}", tool_name=tool, details=f"args{i}")
        h.record_activity(
            "tool_result",
            f"{tool} finished",
            tool_name=tool,
            details=f"Error: permission denied attempt {i}",
        )
    d = assess_handle(h)
    assert d.kind == "thrash"
    assert "failed" in d.guidance.lower() or "error" in d.guidance.lower()


def test_assess_hung() -> None:
    h = _running_handle()
    h.last_activity_at = time.monotonic() - 200
    d = assess_handle(h, policy=SupervisorPolicy(idle_s=90))
    assert d.kind == "hung"


def test_assess_not_running() -> None:
    h = _running_handle()
    h.status = SubAgentStatus.COMPLETED
    d = assess_handle(h)
    assert d.kind == "ok"
    assert not d.needs_intervention


def test_build_loop_guidance_points_to_read_file() -> None:
    text = build_loop_guidance(
        tool="terminal",
        details='{"command": "python -c \\"print(AddressProvider.__init__)\\""}',
        available_tools=["read_file", "grep", "terminal", "write_file"],
        attempt=2,
        max_attempts=3,
    )
    assert "read_file" in text
    assert "python -c" in text or "Protocol" in text
    assert "Attempt 2/3" in text
    last = build_loop_guidance(
        tool="terminal",
        details="same",
        available_tools=["read_file", "ask_user"],
        attempt=3,
        max_attempts=3,
    )
    assert "LAST CHANCE" in last
    assert "ask_user" in last


def test_build_loop_guidance_venv_hunt_says_what_to_fix() -> None:
    text = build_loop_guidance(
        tool="terminal",
        details=(
            '{"command": "cd projects/data_address && '
            "ls .venv/lib/python3.12/site-packages/ | grep -iE 'mako|alemb'\"}"
        ),
        last_result="none\n---\n63",
        available_tools=["read_file", "write_file", "terminal", "ask_user"],
        attempt=1,
        max_attempts=3,
    )
    assert "site-packages" in text or "virtualenv" in text or "venv" in text
    assert "write_file" in text
    assert "Do NOT call `terminal`" in text
    assert "ask_user" in text


def test_format_guidance_system_message() -> None:
    text = format_guidance_system_message(["Do not loop on read_file"])
    assert "supervisor" in text.lower()
    assert "Do not loop" in text


@pytest.mark.asyncio
async def test_supervisor_sends_guidance_with_cap() -> None:
    h = _running_handle("loop-job")
    for _ in range(3):
        h.record_activity(
            "tool_start",
            "Calling read_file",
            tool_name="read_file",
            details="same",
        )
        h.record_activity(
            "tool_result",
            "done",
            tool_name="read_file",
            details="same",
        )

    async_bus = MagicMock()
    async_bus.send = AsyncMock()
    comm = SimpleNamespace(async_bus=async_bus, process_bus=MagicMock())

    manager = MagicMock()
    manager._handles = {"loop-job": h}
    manager._comm_bus = comm
    manager._emit_agent_event = MagicMock()
    manager.notify_progress = MagicMock()
    manager.terminate = AsyncMock(return_value=True)
    manager.interactions = SimpleNamespace(ask_user=AsyncMock(return_value="stop"))

    policy = SupervisorPolicy(
        enabled=True,
        poll_s=1.0,
        idle_s=90.0,
        max_interventions=2,
        cooldown_s=0.0,
        loop_cooldown_s=0.0,
    )
    sup = SubagentSupervisor(manager, policy=policy)

    await sup._maybe_intervene(h)
    assert async_bus.send.await_count == 1
    assert sup._interventions["loop-job"] == 1

    await sup._maybe_intervene(h)
    assert async_bus.send.await_count == 2
    assert sup._interventions["loop-job"] == 2

    # Cap reached — ask the human, then stop if they say stop
    await sup._maybe_intervene(h)
    assert async_bus.send.await_count == 2
    await asyncio.sleep(0)
    manager.interactions.ask_user.assert_awaited()
    manager.terminate.assert_awaited_once_with("loop-job")
    assert h.forced_status == SubAgentStatus.LOOP
    assert h.result is not None
    assert str(h.result.error or "").startswith("loop:")


@pytest.mark.asyncio
async def test_supervisor_does_not_stop_grep_search_loop() -> None:
    h = _running_handle("grep-job")
    h.last_tool = "grep"
    for i in range(4):
        h.record_activity(
            "tool_start",
            "Calling grep",
            tool_name="grep",
            details=f'{{"pattern": "AsyncContainer|{i}", "path": "src/di.py"}}',
        )
        h.record_activity(
            "tool_result",
            "grep finished",
            tool_name="grep",
            details="3 match(es) in 1 file(s)",
        )
        h.steps_taken = i + 1

    async_bus = MagicMock()
    async_bus.send = AsyncMock()
    manager = MagicMock()
    manager._handles = {"grep-job": h}
    manager._comm_bus = SimpleNamespace(async_bus=async_bus, process_bus=MagicMock())
    manager._emit_agent_event = MagicMock()
    manager.notify_progress = MagicMock()
    manager.terminate = AsyncMock(return_value=True)

    sup = SubagentSupervisor(
        manager,
        policy=SupervisorPolicy(
            max_interventions=2,
            cooldown_s=0.0,
            loop_cooldown_s=0.0,
        ),
    )
    await sup._maybe_intervene(h)
    await sup._maybe_intervene(h)
    await sup._maybe_intervene(h)
    manager.terminate.assert_not_awaited()
    assert getattr(h, "forced_status", None) in {None, SubAgentStatus.RUNNING}
    assert h.result is None

    # Exhausted event emitted
    assert manager._emit_agent_event.call_count >= 2


@pytest.mark.asyncio
async def test_supervisor_asks_human_then_injects_reply() -> None:
    h = _running_handle("ask-job")
    for _ in range(3):
        h.record_activity(
            "tool_start",
            "Calling terminal",
            tool_name="terminal",
            details='{"command": "ls .venv/lib/python3.12/site-packages | grep mako"}',
        )
        h.record_activity(
            "tool_result",
            "terminal finished",
            tool_name="terminal",
            details="none",
        )
    h.last_tool = "terminal"

    async_bus = MagicMock()
    async_bus.send = AsyncMock()
    manager = MagicMock()
    manager._handles = {"ask-job": h}
    manager._comm_bus = SimpleNamespace(async_bus=async_bus, process_bus=MagicMock())
    manager._emit_agent_event = MagicMock()
    manager.notify_progress = MagicMock()
    manager.terminate = AsyncMock(return_value=True)
    manager.interactions = SimpleNamespace(
        ask_user=AsyncMock(return_value="uv add nothing; write the FastAPI files")
    )

    sup = SubagentSupervisor(
        manager,
        policy=SupervisorPolicy(max_interventions=1, cooldown_s=0.0, loop_cooldown_s=0.0),
    )
    await sup._maybe_intervene(h)
    await sup._maybe_intervene(h)
    await asyncio.sleep(0)
    manager.interactions.ask_user.assert_awaited()
    manager.terminate.assert_not_awaited()
    assert "human" in async_bus.send.await_args.args[0].content.lower()
    assert sup._interventions["ask-job"] == 0


@pytest.mark.asyncio
async def test_supervisor_respects_cooldown() -> None:
    h = _running_handle("cd-job")
    for _ in range(3):
        h.record_activity(
            "tool_start",
            "Calling x",
            tool_name="read_file",
            details="z",
        )
        h.record_activity("tool_result", "r", tool_name="read_file", details="z")

    async_bus = MagicMock()
    async_bus.send = AsyncMock()
    manager = MagicMock()
    manager._handles = {"cd-job": h}
    manager._comm_bus = SimpleNamespace(async_bus=async_bus, process_bus=MagicMock())
    manager._emit_agent_event = MagicMock()
    manager.notify_progress = MagicMock()

    sup = SubagentSupervisor(
        manager,
        policy=SupervisorPolicy(max_interventions=5, cooldown_s=60.0),
    )
    await sup._maybe_intervene(h)
    await sup._maybe_intervene(h)
    assert async_bus.send.await_count == 1
