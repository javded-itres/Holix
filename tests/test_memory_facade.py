"""Tests for MemoryFacade and memory layer separation."""

import pytest
from core.di.runtime_config import HolixRuntimeConfig
from core.memory.conversation import ConversationStore
from core.memory.facade import MemoryFacade


@pytest.fixture
async def memory_facade(temp_dir):
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        memory_db_path=f"{temp_dir}/memory.db",
        vector_db_path=f"{temp_dir}/vector_db",
        ltm_db_path=f"{temp_dir}/ltm.db",
        skills_dir=f"{temp_dir}/skills",
        enable_long_term_memory=True,
    )
    facade = MemoryFacade(cfg)
    await facade.initialize_db()
    return facade


@pytest.mark.asyncio
async def test_facade_conversation_delegation(memory_facade):
    await memory_facade.save_message("c1", "user", "Hello")
    await memory_facade.save_message("c1", "assistant", "Hi there!")

    messages = await memory_facade.get_conversation("c1", limit=10)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_facade_ltm_store_fact(memory_facade):
    row_id = await memory_facade.store_fact("lang", "Python 3.14", source="test")
    assert row_id > 0

    fact = await memory_facade.get_fact("lang")
    assert fact is not None
    assert "Python" in fact["content"]


@pytest.mark.asyncio
async def test_facade_get_relevant_context(memory_facade):
    await memory_facade.store_fact(
        "api_framework",
        "Holix uses FastAPI for the gateway",
        source="test",
    )

    ctx = await memory_facade.get_relevant_context("FastAPI gateway", top_k=3)
    assert "episodic" in ctx
    assert "semantic" in ctx
    assert "strategic" in ctx


@pytest.mark.asyncio
async def test_facade_ltm_disabled(temp_dir):
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        memory_db_path=f"{temp_dir}/memory.db",
        vector_db_path=f"{temp_dir}/vector_db",
        enable_long_term_memory=False,
    )
    facade = MemoryFacade(cfg)
    await facade.initialize_db()

    await facade.save_message("c1", "user", "test")
    ctx = await facade.get_relevant_context("test")
    assert ctx == {"episodic": [], "semantic": [], "strategic": []}

    with pytest.raises(RuntimeError):
        _ = facade.episodic


@pytest.mark.asyncio
async def test_conversation_store_contract(temp_dir):
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        memory_db_path=f"{temp_dir}/conv.db",
        vector_db_path=f"{temp_dir}/vec",
    )
    store = ConversationStore(cfg)
    await store.initialize_db()

    await store.save_message("ord", "user", "first")
    await store.save_message("ord", "assistant", "second")

    messages = await store.get_conversation("ord", limit=10)
    assert messages[0]["content"] == "first"
    assert messages[1]["content"] == "second"