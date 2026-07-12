"""Streaming tool-call finish_reason quirks (e.g. LiteLLM smart + stop)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.agent_events import ToolCallStartEvent
from core.graph.nodes.react_node import _react_streaming


class _Fn:
    def __init__(self, name: str = "", arguments: str = ""):
        self.name = name
        self.arguments = arguments


class _ToolDelta:
    def __init__(self, index: int, *, id: str = "", name: str = "", arguments: str = ""):
        self.index = index
        self.id = id
        self.function = _Fn(name, arguments)


class _Delta:
    def __init__(self, *, content: str = "", tool_calls: list | None = None):
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, *, delta: _Delta, finish_reason: str | None = None):
        self.delta = delta
        self.finish_reason = finish_reason


class _Chunk:
    def __init__(self, *, delta: _Delta, finish_reason: str | None = None):
        self.choices = [_Choice(delta=delta, finish_reason=finish_reason)]


async def _fake_stream():
    yield _Chunk(
        delta=_Delta(
            tool_calls=[_ToolDelta(0, id="call_1", name="run_terminal_command", arguments='{"command": "pwd"}')],
        ),
        finish_reason=None,
    )
    yield _Chunk(delta=_Delta(), finish_reason="stop")


@pytest.mark.asyncio
async def test_react_streaming_stop_with_tool_deltas_executes_tools() -> None:
    agent = MagicMock()
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_fake_stream())
    agent.client = client
    agent.model = "smart"
    agent.tools.get_schemas.return_value = []
    agent.config = SimpleNamespace(profile_name="default")
    agent.model_manager = None
    agent.emit = MagicMock()

    state = {
        "step_count": 0,
        "conversation_id": "test",
        "messages": [],
    }

    result = await _react_streaming(
        state,
        agent,
        [{"role": "user", "content": "pwd"}],
        1,
        client,
        "smart",
        [],
        0.0,
    )

    assert result["is_final"] is False
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["function"]["name"] == "run_terminal_command"
    started = [
        call.args[0]
        for call in agent.emit.call_args_list
        if call.args and isinstance(call.args[0], ToolCallStartEvent)
    ]
    assert started
    assert started[0].tool_name == "run_terminal_command"