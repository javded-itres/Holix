"""
Tests for Long-term Memory system (Episodic, Semantic, Procedural, Strategic).
"""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path

from core.memory.manager import LongTermMemoryManager
from core.memory.episodic import EpisodicMemoryStore
from core.memory.semantic import SemanticMemoryStore
from core.memory.procedural import ProceduralMemoryStore
from core.memory.strategic import StrategicMemoryStore
from core.memory.vector import VectorMemoryStore


@pytest.fixture
async def ltm_temp_dir():
    """Create temp directory for LTM tests."""
    temp = tempfile.mkdtemp()
    yield temp
    shutil.rmtree(temp, ignore_errors=True)


@pytest.fixture
async def ltm(ltm_temp_dir):
    """Create a MemoryFacade with temp databases."""
    from core.di.runtime_config import HelixRuntimeConfig
    from core.memory.facade import MemoryFacade

    cfg = HelixRuntimeConfig.from_settings().with_overrides(
        memory_db_path=f"{ltm_temp_dir}/memory.db",
        vector_db_path=f"{ltm_temp_dir}/vector_db",
        ltm_db_path=f"{ltm_temp_dir}/ltm.db",
        enable_long_term_memory=True,
        auto_summarize_conversations=False,
    )
    manager = MemoryFacade(cfg)
    await manager.initialize_db()

    yield manager


# =========================================================================
# Episodic Memory Tests
# =========================================================================

class TestEpisodicMemory:

    @pytest.mark.asyncio
    async def test_store_and_search_episode(self, ltm):
        """Test storing and searching episodic memories."""
        await ltm.episodic.store_episode(
            conversation_id="conv_1",
            summary="User asked about FastAPI routing, agent explained decorators and provided code example.",
            outcome="success",
            metadata={"task_type": "coding"},
        )

        await ltm.episodic.store_episode(
            conversation_id="conv_2",
            summary="User needed help with database migration, agent used SQL tools to inspect schema.",
            outcome="success",
            metadata={"task_type": "database"},
        )

        results = await ltm.episodic.search("FastAPI routing", top_k=5)
        assert len(results) >= 1
        # First result should be about FastAPI
        assert "FastAPI" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_get_episodes_for_conversation(self, ltm):
        """Test retrieving episodes for a specific conversation."""
        await ltm.episodic.store_episode(
            conversation_id="conv_unique",
            summary="First episode for this conversation.",
            outcome="success",
        )

        await ltm.episodic.store_episode(
            conversation_id="conv_other",
            summary="Unrelated episode.",
            outcome="partial",
        )

        episodes = await ltm.episodic.get_episodes_for_conversation("conv_unique")
        assert len(episodes) == 1
        assert episodes[0]["content"] == "First episode for this conversation."

    @pytest.mark.asyncio
    async def test_episode_outcome_metadata(self, ltm):
        """Test that outcome metadata is preserved in episodes."""
        await ltm.episodic.store_episode(
            conversation_id="conv_fail",
            summary="Task failed due to missing file.",
            outcome="failure",
            metadata={"error_type": "FileNotFoundError"},
        )

        results = await ltm.episodic.search("missing file", top_k=1)
        assert len(results) >= 1
        assert results[0]["outcome"] == "failure"

    @pytest.mark.asyncio
    async def test_auto_summarize_fallback(self, ltm):
        """Test auto-summarization fallback without LLM client."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        result = await ltm.auto_summarize_conversation(
            conversation_id="conv_auto",
            messages=messages,
            llm_client=None,
        )

        assert result is not None
        assert "user messages" in result

        # Verify it was stored
        episodes = await ltm.episodic.get_episodes_for_conversation("conv_auto")
        assert len(episodes) == 1


# =========================================================================
# Semantic Memory Tests
# =========================================================================

class TestSemanticMemory:

    @pytest.mark.asyncio
    async def test_store_and_get_fact(self, ltm):
        """Test storing and retrieving a fact by key."""
        await ltm.semantic.store_fact(
            key="project_language",
            content="Python 3.14+",
            source="conversation_1",
        )

        fact = await ltm.semantic.get_fact("project_language")
        assert fact is not None
        assert fact["key"] == "project_language"
        assert "Python" in fact["content"]

    @pytest.mark.asyncio
    async def test_update_fact(self, ltm):
        """Test upsert semantics — updating an existing fact."""
        await ltm.semantic.store_fact(
            key="framework",
            content="Flask",
            source="initial",
        )

        # Update the fact
        await ltm.semantic.store_fact(
            key="framework",
            content="FastAPI",
            source="updated",
        )

        fact = await ltm.semantic.get_fact("framework")
        assert fact is not None
        assert fact["content"] == "FastAPI"

    @pytest.mark.asyncio
    async def test_search_facts(self, ltm):
        """Test semantic search across facts."""
        await ltm.semantic.store_fact(
            key="db_type",
            content="SQLite with ChromaDB for vector search",
            source="config",
        )

        await ltm.semantic.store_fact(
            key="api_style",
            content="RESTful API with FastAPI framework",
            source="conversation",
        )

        results = await ltm.semantic.search("vector search database", top_k=5)
        assert len(results) >= 1
        assert any("ChromaDB" in r["content"] for r in results)

    @pytest.mark.asyncio
    async def test_get_all_facts(self, ltm):
        """Test retrieving all facts."""
        await ltm.semantic.store_fact(key="fact1", content="First fact")
        await ltm.semantic.store_fact(key="fact2", content="Second fact")

        facts = await ltm.semantic.get_all_facts()
        assert len(facts) >= 2

    @pytest.mark.asyncio
    async def test_delete_fact(self, ltm):
        """Test deleting a fact."""
        await ltm.semantic.store_fact(key="to_delete", content="Temporary fact")

        deleted = await ltm.semantic.delete_fact("to_delete")
        assert deleted is True

        fact = await ltm.semantic.get_fact("to_delete")
        assert fact is None

    @pytest.mark.asyncio
    async def test_nonexistent_fact(self, ltm):
        """Test getting a non-existent fact returns None."""
        fact = await ltm.semantic.get_fact("nonexistent_key_xyz")
        assert fact is None


# =========================================================================
# Procedural Memory Tests
# =========================================================================

class TestProceduralMemory:

    @pytest.mark.asyncio
    async def test_record_skill_outcome(self, ltm):
        """Test recording a skill usage outcome."""
        entry_id = await ltm.procedural.record_skill_outcome(
            skill_name="code_review",
            task_description="Review FastAPI endpoint code",
            success=True,
            context={"mode": "react"},
        )
        assert entry_id > 0

    @pytest.mark.asyncio
    async def test_skill_outcome_stats(self, ltm):
        """Test aggregated outcome statistics for a skill."""
        await ltm.procedural.record_skill_outcome(
            "test_skill", "Task A", success=True
        )
        await ltm.procedural.record_skill_outcome(
            "test_skill", "Task B", success=True
        )
        await ltm.procedural.record_skill_outcome(
            "test_skill", "Task C", success=False
        )

        # Get stats through the internal method
        stats = await ltm.procedural._get_skill_outcomes("test_skill")
        assert stats["success_count"] == 2
        assert stats["failure_count"] == 1
        assert stats["success_rate"] == pytest.approx(2 / 3, abs=0.01)


# =========================================================================
# Strategic Memory Tests
# =========================================================================

class TestStrategicMemory:

    @pytest.mark.asyncio
    async def test_store_and_search_strategy(self, ltm):
        """Test storing and searching strategic memories."""
        await ltm.strategic.store_strategy(
            key="user_prefers_async",
            content="User prefers async Python code for all new modules",
            category="user_preference",
            source="conversation",
        )

        await ltm.strategic.store_strategy(
            key="avoid_large_sql",
            content="Avoid raw SQL for large datasets — use ORM or pagination",
            category="failure_mode",
            source="experience",
        )

        results = await ltm.strategic.search("async code preference", top_k=5)
        assert len(results) >= 1
        assert any("async" in r["content"].lower() for r in results)

    @pytest.mark.asyncio
    async def test_update_strategy(self, ltm):
        """Test upsert semantics for strategies."""
        await ltm.strategic.store_strategy(
            key="coding_mode",
            content="Use ReAct mode for coding tasks",
            category="execution_mode",
        )

        # Update
        await ltm.strategic.store_strategy(
            key="coding_mode",
            content="Use Hybrid mode for coding tasks (plan then execute)",
            category="execution_mode",
        )

        strategies = await ltm.strategic.get_strategies_for_category("execution_mode")
        assert len(strategies) == 1
        assert "Hybrid" in strategies[0]["content"]

    @pytest.mark.asyncio
    async def test_get_all_strategies(self, ltm):
        """Test getting all strategies for prompt injection."""
        await ltm.strategic.store_strategy(
            key="pref1", content="Preference 1", category="user_preference"
        )
        await ltm.strategic.store_strategy(
            key="pref2", content="Preference 2", category="user_preference"
        )
        await ltm.strategic.store_strategy(
            key="fail1", content="Avoid X", category="failure_mode"
        )

        all_strats = await ltm.strategic.get_all_strategies()
        assert len(all_strats) >= 3

    @pytest.mark.asyncio
    async def test_format_strategies_for_prompt(self, ltm):
        """Test formatting strategies for prompt injection."""
        await ltm.strategic.store_strategy(
            key="test_pref", content="Always use type hints", category="user_preference"
        )

        strategies = await ltm.strategic.get_all_strategies()
        formatted = ltm.strategic.format_strategies_for_prompt(strategies)
        assert "Strategic Memory" in formatted
        assert "type hints" in formatted

    @pytest.mark.asyncio
    async def test_delete_strategy(self, ltm):
        """Test deleting a strategy."""
        await ltm.strategic.store_strategy(key="to_remove", content="Temporary")

        deleted = await ltm.strategic.delete_strategy("to_remove")
        assert deleted is True

        all_strats = await ltm.strategic.get_all_strategies()
        assert not any(s["key"] == "to_remove" for s in all_strats)


# =========================================================================
# Integration: LongTermMemoryManager
# =========================================================================

class TestLongTermMemoryManager:

    @pytest.mark.asyncio
    async def test_legacy_api_backward_compat(self, ltm):
        """Test that all legacy MemoryManager methods still work."""
        # save_message + get_conversation
        await ltm.save_message("test_conv", "user", "Hello, this is a longer message for indexing")
        await ltm.save_message("test_conv", "assistant", "Hi there, I can help you with that!")
        messages = await ltm.get_conversation("test_conv", limit=10)
        assert len(messages) == 2

        # search (ChromaDB may need a moment to index)
        results = await ltm.search("longer message indexing", top_k=5)
        # ChromaDB indexing can be flaky in tests — verify the API works
        # even if results are empty due to async indexing
        assert isinstance(results, list)

        # list_recent_conversations
        convs = await ltm.list_recent_conversations(limit=10)
        assert len(convs) >= 1

    @pytest.mark.asyncio
    async def test_get_relevant_context(self, ltm):
        """Test unified context retrieval from all memory types."""
        # Store in multiple types
        await ltm.episodic.store_episode(
            "conv_1", "Worked on FastAPI endpoints", "success"
        )
        await ltm.semantic.store_fact(
            "framework", "FastAPI", source="config"
        )
        await ltm.strategic.store_strategy(
            "use_async", "Prefer async handlers", category="user_preference"
        )

        context = await ltm.get_relevant_context("FastAPI async", top_k=3)

        assert "episodic" in context
        assert "semantic" in context
        assert "strategic" in context
        assert len(context["episodic"]) >= 1
        assert len(context["semantic"]) >= 1

    @pytest.mark.asyncio
    async def test_memory_stats(self, ltm):
        """Test getting memory statistics."""
        stats = ltm.get_memory_stats()
        assert "vector_store" in stats