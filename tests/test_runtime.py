"""Tests for unified runtime (session + executor)."""

import pytest

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
    assert len(messages) == 2
    assert messages[0]["role"] == "assistant"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "New question"


@pytest.mark.asyncio
async def test_conversation_messages_chronological_order(memory_manager):
    """Recent messages are returned oldest-first (stable via id ordering)."""
    conv_id = "order_test"
    await memory_manager.save_message(conv_id, "user", "First")
    await memory_manager.save_message(conv_id, "assistant", "Second")

    messages = await memory_manager.get_conversation(conv_id, limit=10)

    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"