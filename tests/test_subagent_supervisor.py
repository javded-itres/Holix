"""Tests for runtime Subagent Supervisor (detect + guidance)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.subagents.base import SubAgentConfig, SubAgentHandle, SubAgentStatus
from core.subagents.supervisor import (
    SubagentSupervisor,
    SupervisorPolicy,
    assess_handle,
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

    policy = SupervisorPolicy(
        enabled=True,
        poll_s=1.0,
        idle_s=90.0,
        max_interventions=2,
        cooldown_s=0.0,
    )
    sup = SubagentSupervisor(manager, policy=policy)

    await sup._maybe_intervene(h)
    assert async_bus.send.await_count == 1
    assert sup._interventions["loop-job"] == 1

    await sup._maybe_intervene(h)
    assert async_bus.send.await_count == 2
    assert sup._interventions["loop-job"] == 2

    # Cap reached — no more sends
    await sup._maybe_intervene(h)
    assert async_bus.send.await_count == 2

    # Exhausted event emitted
    assert manager._emit_agent_event.call_count >= 2


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
