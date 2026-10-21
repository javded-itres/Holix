"""Session context compression helpers."""

from __future__ import annotations

from datetime import UTC

import pytest
from core.context.manager import ContextManager
from core.context.token_counter import TokenCounter
from core.graph.routers import route_after_react
from core.graph.state import HolixGraphState
from core.memory.tool_content import truncate_tool_content_for_memory
from core.profile.soul import inject_soul_into_messages, is_soul_message
from core.runtime.context_session import compress_session_if_needed


@pytest.mark.asyncio
async def test_compress_session_does_not_persist_honesty_nudges() -> None:
    from unittest.mock import AsyncMock, MagicMock

    class _CM:
        last_summary = ""

        async def auto_compress_if_needed(self, messages, conversation_id=None):
            return list(messages), True

        def invalidate_usage_cache(self, conversation_id):
            return None

    agent = MagicMock()
    agent.config.profile_name = "default"
    agent.context_manager = _CM()
    agent.memory.replace_conversation_messages = AsyncMock(return_value=2)
    messages = [
        {"role": "user", "content": "сделай пост"},
        {"role": "assistant", "content": "Создаю…"},
        {
            "role": "user",
            "content": "[Action honesty — tools] You are only narrating progress",
        },
    ]
    out, was = await compress_session_if_needed(agent, "c1", messages)
    assert was is True
    stored = agent.memory.replace_conversation_messages.await_args.args[1]
    assert any(
        isinstance(m, dict) and str(m.get("content") or "").startswith("[Action honesty")
        for m in out
    )
    assert all(
        not (
            isinstance(m, dict)
            and str(m.get("content") or "").strip().startswith("[Action honesty")
        )
        for m in stored
    )


@pytest.mark.asyncio
async def test_compress_session_at_95_percent() -> None:
    counter = TokenCounter()
    manager = ContextManager(
        context_window=1000,
        token_counter=counter,
        compressor=None,
    )

    class _Agent:
        context_manager = manager
        memory = None

    messages = [{"role": "user", "content": "x" * 8000}]
    usage = manager.get_usage(messages, include_system_reserve=True)
    assert usage["percent"] >= manager.compression_threshold * 100

    out, was = await compress_session_if_needed(_Agent(), "c1", messages)
    assert was is False
    assert is_soul_message(out[0])
    assert out[1:] == messages
    assert out == inject_soul_into_messages(messages, "default")


@pytest.mark.asyncio
async def test_idle_compress_runs_once_per_quiet_gap() -> None:
    from types import SimpleNamespace

    from core.runtime.context_session import _idle_compress

    calls = {"n": 0}

    class _CM:
        warning_threshold = 0.55

        def get_usage(self, messages, conversation_id=None, include_system_reserve=False):
            return {"percent": 60.0}

        async def compress_context(self, messages):
            calls["n"] += 1
            return [{"role": "system", "content": "Context compressed"}, *messages[-1:]], True

    agent = SimpleNamespace(
        context_manager=_CM(),
        _session_last_activity={"c1": "2020-01-01 00:00:00"},
    )
    messages = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
        {"role": "assistant", "content": "d"},
    ]
    out, was = await _idle_compress(agent, "c1", messages)
    assert was is True
    assert out[0]["content"] == "Context compressed"
    _, again = await _idle_compress(agent, "c1", messages)
    assert again is False
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_idle_compress_skips_a_fresh_session() -> None:
    from datetime import datetime
    from types import SimpleNamespace

    from core.runtime.context_session import _idle_compress

    class _CM:
        warning_threshold = 0.55

        def get_usage(self, messages, conversation_id=None, include_system_reserve=False):
            raise AssertionError("fresh session must not be measured for idle compress")

        async def compress_context(self, messages):
            raise AssertionError("fresh session must not be compressed")

    agent = SimpleNamespace(
        context_manager=_CM(),
        _session_last_activity={
            "c1": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        },
    )
    messages = [{"role": "user", "content": str(i)} for i in range(4)]
    out, was = await _idle_compress(agent, "c1", messages)
    assert was is False
    assert out == messages


def test_route_after_react_respects_max_steps_with_tools() -> None:
    state = HolixGraphState(
        tool_calls=[{"id": "t1", "function": {"name": "read_file", "arguments": "{}"}}],
        step_count=15,
        max_steps=15,
        is_final=False,
    )
    assert route_after_react(state) == "reflect"


def test_route_after_react_unlimited_max_steps_keeps_tools() -> None:
    state = HolixGraphState(
        tool_calls=[{"id": "t1", "function": {"name": "read_file", "arguments": "{}"}}],
        step_count=500,
        max_steps=0,
        is_final=False,
    )
    assert route_after_react(state) == "tool_execution"


def test_truncate_tool_content_for_memory() -> None:
    big = "a" * 20_000
    out = truncate_tool_content_for_memory(big, max_chars=100)
    assert len(out) < len(big)
    assert "truncated for memory" in out


def test_sanitize_messages_tool_content_stale_tools_tighter() -> None:
    from core.memory.tool_content import (
        GRAPH_TOOL_MAX_CHARS,
        STALE_TOOL_MAX_CHARS,
        sanitize_messages_tool_content,
    )

    dump = "LOG\n" + ("x" * 5000)
    messages = [{"role": "user", "content": "go"}]
    for i in range(10):
        messages.append({"role": "tool", "content": dump, "name": f"t{i}"})
    out = sanitize_messages_tool_content(messages)
    stale = out[1]["content"]
    recent = out[-1]["content"]
    assert len(stale) <= STALE_TOOL_MAX_CHARS + 120
    assert len(recent) <= GRAPH_TOOL_MAX_CHARS + 120
    assert len(stale) < len(recent)


def test_conversation_history_limit_is_the_whole_session() -> None:
    from types import SimpleNamespace

    from core.runtime.session import conversation_history_limit

    assert conversation_history_limit(None) is None
    capped = SimpleNamespace(config=SimpleNamespace(conversation_history_limit=40))
    assert conversation_history_limit(capped) == 40
    unlimited = SimpleNamespace(config=SimpleNamespace(conversation_history_limit=0))
    assert conversation_history_limit(unlimited) is None


def test_sanitize_messages_tool_content_caps_runaway_terminal() -> None:
    from core.memory.tool_content import (
        GRAPH_TOOL_MAX_CHARS,
        sanitize_messages_tool_content,
    )

    huge = "Success (exit code 0):\n" + ("line\n" * 500_000)
    messages = [
        {"role": "user", "content": "find bug"},
        {"role": "tool", "content": huge},
        {"role": "assistant", "content": "ok"},
    ]
    out = sanitize_messages_tool_content(messages)
    assert len(out[1]["content"]) <= GRAPH_TOOL_MAX_CHARS + 120
    assert "truncated for context" in out[1]["content"]
    # usage must not report multi-window overflow
    manager = ContextManager(context_window=8_000, token_counter=TokenCounter())
    usage = manager.get_usage(messages)
    assert usage["percent"] < 200  # still bounded; unsanitized would be thousands %
