"""Cross-session memory search tools and formatting."""

from __future__ import annotations

import pytest
from core.memory.conversation import _SEARCHABLE_ROLES
from core.memory.session_search import (
    format_memory_hit_line,
    format_memory_search_results,
    format_session_transcript,
)
from core.tools.execution_context import (
    conversation_scope,
    memory_facade_scope,
    reset_conversation_scope,
    reset_memory_facade_scope,
)
from core.tools.session_memory import ReadSessionTool, SearchSessionsTool


def test_searchable_roles_exclude_tool() -> None:
    assert "tool" not in _SEARCHABLE_ROLES
    assert "user" in _SEARCHABLE_ROLES
    assert "assistant" in _SEARCHABLE_ROLES
    assert "system" in _SEARCHABLE_ROLES


def test_format_memory_hit_line_shows_session() -> None:
    line = format_memory_hit_line(
        {
            "content": "Hello from another chat",
            "metadata": {
                "conversation_id": "tui_default_99",
                "role": "assistant",
            },
            "distance": 0.2,
        },
        index=1,
    )
    assert "tui_default_99" in line
    assert "assistant" in line
    assert "Hello" in line


def test_format_memory_search_results_skips_current_session() -> None:
    results = [
        {
            "content": "current session msg",
            "metadata": {"conversation_id": "sess-a", "role": "user"},
        },
        {
            "content": "other session msg",
            "metadata": {"conversation_id": "sess-b", "role": "user"},
        },
    ]
    text = format_memory_search_results(
        results,
        current_conversation_id="sess-a",
        include_current=False,
    )
    assert "sess-b" in text
    assert "sess-a" not in text


def test_format_session_transcript() -> None:
    text = format_session_transcript(
        "tg_1",
        [
            {"role": "user", "content": "Hi"},
            {"role": "tool", "content": "ok", "metadata": {"tool_name": "read_file"}},
        ],
    )
    assert "tg_1" in text
    assert "read_file" in text
    assert "Hi" in text


@pytest.mark.asyncio
async def test_search_sessions_tool(memory_manager) -> None:
    await memory_manager.save_message("sess-a", "user", "Deploy kubernetes helm chart steps")
    await memory_manager.save_message("sess-b", "user", "Weather in Moscow today")

    tool = SearchSessionsTool()
    mem_token = memory_facade_scope(memory_manager)
    conv_token = conversation_scope("sess-b")
    try:
        out = await tool.execute(query="kubernetes helm", top_k=5)
    finally:
        reset_memory_facade_scope(mem_token)
        reset_conversation_scope(conv_token)

    assert "sess-a" in out
    assert "helm" in out.lower()


@pytest.mark.asyncio
async def test_read_session_tool(memory_manager) -> None:
    await memory_manager.save_message("hist-1", "user", "Remember this secret code: alpha")
    await memory_manager.save_message("hist-1", "assistant", "Noted alpha code")

    tool = ReadSessionTool()
    mem_token = memory_facade_scope(memory_manager)
    try:
        out = await tool.execute(conversation_id="hist-1", limit=10)
    finally:
        reset_memory_facade_scope(mem_token)

    assert "hist-1" in out
    assert "alpha" in out


@pytest.mark.asyncio
async def test_tool_messages_excluded_from_search_but_kept_in_history(
    memory_manager,
) -> None:
    conv_id = "tool-sess"
    long_tool_output = "x" * 50
    await memory_manager.save_message(
        conv_id,
        "user",
        "Run diagnostics on the kubernetes cluster please",
    )
    await memory_manager.save_message(
        conv_id,
        "tool",
        long_tool_output,
        metadata={"tool_name": "run_terminal_command"},
    )
    await memory_manager.save_message(
        conv_id,
        "assistant",
        "Diagnostics finished: cluster is healthy",
    )

    history = await memory_manager.get_conversation(conv_id, limit=10)
    assert len(history) == 3
    assert any(m["role"] == "tool" for m in history)

    results = await memory_manager.search("kubernetes diagnostics", top_k=5)
    assert results
    assert not any(r.get("metadata", {}).get("role") == "tool" for r in results)
    assert any(r.get("metadata", {}).get("role") in {"user", "assistant"} for r in results)


@pytest.mark.asyncio
async def test_registry_registers_session_tools() -> None:
    from core.tools.registry import ToolRegistry

    reg = ToolRegistry()
    reg.register_all()
    names = reg.get_tool_names()
    assert "search_sessions" in names
    assert "read_session" in names