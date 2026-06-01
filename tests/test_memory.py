import pytest


@pytest.mark.asyncio
async def test_save_and_retrieve_message(memory_manager):
    """Test saving and retrieving messages."""
    conv_id = "test_conversation"

    # Save message
    await memory_manager.save_message(
        conv_id,
        "user",
        "Hello, agent!"
    )

    await memory_manager.save_message(
        conv_id,
        "assistant",
        "Hello! How can I help you?"
    )

    # Retrieve messages
    messages = await memory_manager.get_conversation(conv_id, limit=10)

    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello, agent!"
    assert messages[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_semantic_search(memory_manager):
    """Test semantic memory search."""
    conv_id = "test_search"

    # Add some messages
    await memory_manager.save_message(
        conv_id,
        "user",
        "How do I create a FastAPI endpoint?"
    )

    await memory_manager.save_message(
        conv_id,
        "assistant",
        "To create a FastAPI endpoint, use the @app.get() decorator"
    )

    # Search
    results = await memory_manager.search("FastAPI endpoint", top_k=5)

    # Should find related messages
    assert len(results) > 0
