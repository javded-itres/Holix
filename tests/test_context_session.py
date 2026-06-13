"""Session context compression helpers."""

from __future__ import annotations

import pytest
from core.context.manager import ContextManager
from core.context.token_counter import TokenCounter
from core.graph.routers import route_after_react
from core.graph.state import HolixGraphState
from core.memory.tool_content import truncate_tool_content_for_memory
from core.profile.soul import inject_soul_into_messages, is_soul_message
from core.runtime.context_session import compress_session_if_needed


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
    usage = manager.get_usage(messages)
    assert usage["percent"] >= manager.compression_threshold * 100

    out, was = await compress_session_if_needed(_Agent(), "c1", messages)
    assert was is False
    assert is_soul_message(out[0])
    assert out[1:] == messages
    assert out == inject_soul_into_messages(messages, "default")


def test_route_after_react_respects_max_steps_with_tools() -> None:
    state = HolixGraphState(
        tool_calls=[{"id": "t1", "function": {"name": "read_file", "arguments": "{}"}}],
        step_count=15,
        max_steps=15,
        is_final=False,
    )
    assert route_after_react(state) == "finalize"


def test_truncate_tool_content_for_memory() -> None:
    big = "a" * 20_000
    out = truncate_tool_content_for_memory(big, max_chars=100)
    assert len(out) < len(big)
    assert "truncated for memory" in out