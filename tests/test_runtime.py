"""Tests for unified runtime (session + executor)."""

import pytest
from core.profile.soul import is_soul_message
from core.runtime.session import prepare_session


@pytest.mark.asyncio
async def test_prepare_session_appends_user_message(memory_manager):
    """prepare_session persists user input and returns updated messages."""
    agent = type("Agent", (), {})()
    agent.memory = memory_manager
    agent.context_manager = None

    await memory_manager.save_message("conv1", "assistant", "Hi")

    messages, compressed = await prepare_session(agent, "New question", "conv1")

    assert compressed is False
    assert len(messages) == 3
    assert is_soul_message(messages[0])
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"
    assert messages[2]["content"] == "New question"


@pytest.mark.asyncio
async def test_prepare_session_loads_full_recent_history(memory_manager):
    """Agent must see more than the legacy 30-message window (tool-heavy runs)."""
    agent = type("Agent", (), {})()
    agent.memory = memory_manager
    agent.context_manager = None
    agent.config = None

    conv_id = "studio_heavy"
    for i in range(45):
        await memory_manager.save_message(conv_id, "tool", f"tool output {i}")

    messages, compressed = await prepare_session(agent, "continue task", conv_id)

    assert compressed is False
    roles = [m["role"] for m in messages if not is_soul_message(m)]
    assert roles.count("tool") == 45
    assert messages[-1]["content"] == "continue task"


@pytest.mark.asyncio
async def test_conversation_messages_chronological_order(memory_manager):
    """Recent messages are returned oldest-first (stable via id ordering)."""
    conv_id = "order_test"
    await memory_manager.save_message(conv_id, "user", "First")
    await memory_manager.save_message(conv_id, "assistant", "Second")

    messages = await memory_manager.get_conversation(conv_id, limit=10)

    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"