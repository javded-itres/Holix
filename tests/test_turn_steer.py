"""Steer the running turn, and group read-only tool calls."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from core.graph.nodes.tool_batches import group_tool_calls
from core.graph.nodes.tool_execution_node import tool_execution_node
from core.runtime.turn_steer import SteerBox, absorb_steer, reset_steer_scope, steer_scope


class _Tool:
    def __init__(self, risk: str) -> None:
        self.risk_level = risk


def test_group_tool_calls_batches_only_consecutive_reads() -> None:
    agent = SimpleNamespace(
        tools=SimpleNamespace(
            tools={
                "read_file": _Tool("no"),
                "glob": _Tool("no"),
                "write_file": _Tool("write"),
                "ask_user": _Tool("no"),
                "enter_plan_mode": _Tool("no"),
            }
        )
    )
    calls = [
        {"function": {"name": "read_file"}},
        {"function": {"name": "glob"}},
        {"function": {"name": "write_file"}},
        {"function": {"name": "read_file"}},
        {"function": {"name": "ask_user"}},
        {"function": {"name": "read_file"}},
        {"function": {"name": "enter_plan_mode"}},
    ]
    groups = group_tool_calls(agent, calls)
    assert [[c["function"]["name"] for c in group] for group in groups] == [
        ["read_file", "glob"],
        ["write_file"],
        ["read_file"],
        ["ask_user"],
        ["read_file"],
        ["enter_plan_mode"],
    ]


@pytest.mark.asyncio
async def test_absorb_steer_appends_and_saves_once() -> None:
    box = SteerBox()
    token = steer_scope(box)
    try:
        box.push("  stop and check the host  ")
        box.push("")
        memory = SimpleNamespace(save_message=AsyncMock())
        messages: list[dict] = [{"role": "assistant", "content": "running"}]
        assert await absorb_steer(messages, SimpleNamespace(memory=memory), "c1") is True
        assert messages[-1] == {"role": "user", "content": "stop and check the host"}
        memory.save_message.assert_awaited_once_with("c1", "user", "stop and check the host")
        assert await absorb_steer(messages, SimpleNamespace(memory=memory), "c1") is False
        assert box.drain() == []
    finally:
        reset_steer_scope(token)


def _agent(registry: object) -> SimpleNamespace:
    return SimpleNamespace(
        client=None,
        model=None,
        config=None,
        memory=SimpleNamespace(save_message=AsyncMock()),
        tools=registry,
        skills=None,
        context_manager=None,
        events=None,
        agent_slot="main",
    )


class _Registry:
    def __init__(self) -> None:
        self.tools = {
            "read_file": _Tool("no"),
            "write_file": _Tool("write"),
        }
        self._action_guard = None
        self.started: list[tuple[str, float]] = []

    async def execute(self, tc, conversation_id=None, memory=None):
        self.started.append((tc.function.name, asyncio.get_running_loop().time()))
        await asyncio.sleep(0.08)
        return f"ok {tc.function.name}"


def _call(tool_id: str, name: str) -> dict:
    return {"id": tool_id, "function": {"name": name, "arguments": "{}"}}


@pytest.mark.asyncio
async def test_read_only_tools_in_one_step_overlap() -> None:
    registry = _Registry()
    out = await tool_execution_node(
        {
            "tool_calls": [
                _call("1", "read_file"),
                _call("2", "read_file"),
                _call("3", "write_file"),
            ],
            "messages": [],
            "conversation_id": "c",
        },
        {"configurable": {"_agent": _agent(registry)}},
    )
    names = [name for name, _ in registry.started]
    assert names == ["read_file", "read_file", "write_file"]
    assert registry.started[1][1] - registry.started[0][1] < 0.05
    assert registry.started[2][1] - registry.started[0][1] >= 0.08
    assert "is_final" not in out
    assert [m["role"] for m in out["messages"]] == ["tool", "tool", "tool"]


@pytest.mark.asyncio
async def test_pending_steer_skips_tools_and_keeps_the_turn_open() -> None:
    registry = _Registry()
    box = SteerBox()
    token = steer_scope(box)
    try:
        box.push("use the other file")
        out = await tool_execution_node(
            {
                "tool_calls": [_call("1", "read_file"), _call("2", "write_file")],
                "messages": [],
                "conversation_id": "c",
            },
            {"configurable": {"_agent": _agent(registry)}},
        )
    finally:
        reset_steer_scope(token)
    assert registry.started == []
    assert out.get("is_final") is not True
    assert "is_final" not in out
    texts = [m["content"] for m in out["messages"]]
    assert texts[-1] == "use the other file"
    assert all("not executed" in text for text in texts[:-1])
