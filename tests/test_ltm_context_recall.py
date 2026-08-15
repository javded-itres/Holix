"""
Context-recall tests for short-term (conversation) vs long-term memory.

Covers:
- paraphrase / semantic retrieval of LTM facts, episodes, strategies
- memory_retrieval_node injecting LTM + conversation hits into graph state
- /forget clears conversation store but not LTM
- LTM is profile-scoped (not project-scoped); two profiles do not share LTM
- conversation messages are conversation_id-scoped; LTM is shared across
  conversations inside the same profile
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from core.di.runtime_config import HolixRuntimeConfig
from core.memory.facade import MemoryFacade


def _unique_collection(request) -> str:
    import re
    import uuid

    safe = re.sub(r"[^\w]", "_", request.node.name)[:48]
    return f"ltm_recall_{safe}_{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def ltm_facade(temp_dir, request):
    """Isolated MemoryFacade with LTM enabled under temp_dir."""
    root = Path(temp_dir)
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        memory_db_path=str(root / "memory.db"),
        vector_db_path=str(root / "vector_db"),
        ltm_db_path=str(root / "ltm.db"),
        memory_chroma_collection=_unique_collection(request),
        enable_long_term_memory=True,
        auto_summarize_conversations=False,
    )
    facade = MemoryFacade(cfg)
    await facade.initialize_db()
    return facade


def _make_facade(root: Path, *, collection: str) -> MemoryFacade:
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        memory_db_path=str(root / "memory.db"),
        vector_db_path=str(root / "vector_db"),
        ltm_db_path=str(root / "ltm.db"),
        memory_chroma_collection=collection,
        enable_long_term_memory=True,
        auto_summarize_conversations=False,
    )
    return MemoryFacade(cfg)


# ---------------------------------------------------------------------------
# Semantic / episodic / strategic recall by paraphrase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semantic_paraphrase_recall(ltm_facade):
    """Fact stored in one wording is found by a different natural-language query."""
    await ltm_facade.store_fact(
        key="deploy_target",
        content="Production Holix Studio is deployed only via GitHub Actions on branch main",
        source="test",
    )
    await ltm_facade.store_fact(
        key="snack_pref",
        content="The user prefers green tea over coffee in the morning",
        source="test",
    )

    # Paraphrase — not a keyword substring of the stored fact.
    ctx = await ltm_facade.get_relevant_context(
        "How do we ship Studio to production?",
        top_k=3,
    )
    semantic = ctx["semantic"]
    assert semantic, "expected at least one semantic hit"
    joined = " ".join(r.get("content", "") for r in semantic).lower()
    assert "github actions" in joined or "main" in joined
    assert any(
        "deploy" in (r.get("key") or "") or "github" in r.get("content", "").lower()
        for r in semantic
    )


@pytest.mark.asyncio
async def test_semantic_ranks_relevant_above_noise(ltm_facade):
    """Closer topical query should surface the matching fact first."""
    await ltm_facade.store_fact(
        key="db_engine",
        content="Project database is PostgreSQL 16 with asyncpg",
        source="test",
    )
    await ltm_facade.store_fact(
        key="ui_theme",
        content="Studio dark theme uses zinc-950 background",
        source="test",
    )

    results = await ltm_facade.semantic.search(
        "what database and driver do we use?",
        top_k=2,
    )
    assert results
    top = results[0]
    blob = f"{top.get('key', '')} {top.get('content', '')}".lower()
    assert "postgres" in blob or "asyncpg" in blob or "db_engine" in blob


@pytest.mark.asyncio
async def test_episodic_paraphrase_recall(ltm_facade):
    """Past episode summary is recallable by a related task description."""
    await ltm_facade.episodic.store_episode(
        conversation_id="conv_a",
        summary=(
            "User needed nginx reverse-proxy for Holix gateway on port 8080; "
            "agent wrote a server block with WebSocket upgrade headers."
        ),
        outcome="success",
        metadata={"task_type": "ops"},
    )
    await ltm_facade.episodic.store_episode(
        conversation_id="conv_b",
        summary="User asked how to rename a profile; agent explained holix profile rename.",
        outcome="success",
    )

    hits = await ltm_facade.search_episodes(
        "configure reverse proxy for the API gateway",
        top_k=3,
    )
    assert hits
    assert any("nginx" in h.get("content", "").lower() for h in hits)


@pytest.mark.asyncio
async def test_strategic_paraphrase_recall(ltm_facade):
    """User preference stored as strategy is found by paraphrased query."""
    await ltm_facade.store_strategy(
        key="prefer_typed_python",
        content="Always add type hints and prefer pathlib over os.path",
        category="user_preference",
        source="conversation",
    )
    await ltm_facade.store_strategy(
        key="avoid_shell_rm",
        content="Never run rm -rf without explicit user confirmation",
        category="safety",
        source="policy",
    )

    hits = await ltm_facade.search_strategies(
        "how should I write Python code style?",
        top_k=3,
    )
    assert hits
    joined = " ".join(h.get("content", "") for h in hits).lower()
    assert "type hint" in joined or "pathlib" in joined


@pytest.mark.asyncio
async def test_get_relevant_context_merges_all_ltm_types(ltm_facade):
    """Unified retrieval returns episodic + semantic + strategic for one query."""
    await ltm_facade.episodic.store_episode(
        "c1",
        "Debugged Chroma embeddings on Apple Silicon CPU path",
        "success",
    )
    await ltm_facade.store_fact(
        "embedder",
        "Holix uses ONNX MiniLM embeddings for Chroma on CPU",
        source="docs",
    )
    await ltm_facade.store_strategy(
        "slow_cpu",
        "On weak CPUs prefer smaller top_k for vector search",
        category="performance",
    )

    ctx = await ltm_facade.get_relevant_context("Chroma vector embeddings CPU", top_k=5)
    assert ctx["episodic"]
    assert ctx["semantic"]
    assert ctx["strategic"]
    assert any(
        "ONNX" in r.get("content", "") or "MiniLM" in r.get("content", "") for r in ctx["semantic"]
    )


# ---------------------------------------------------------------------------
# Conversation (STM) vs LTM scope inside one profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conversation_search_scoped_by_id_ltm_is_global(ltm_facade):
    """STM search can filter by conversation_id; LTM facts ignore conversation_id."""
    await ltm_facade.save_message(
        "session-alice",
        "user",
        "My secret project codename is Nebula Gate for the Alice session only",
    )
    await ltm_facade.save_message(
        "session-bob",
        "user",
        "Bob session talks about inventory microservices and Kafka only",
    )
    await ltm_facade.store_fact(
        "shared_fact",
        "Company timezone for deploys is Europe/Moscow",
        source="session-alice",
    )

    alice_hits = await ltm_facade.search(
        "Nebula Gate codename",
        top_k=5,
        conversation_id="session-alice",
    )
    bob_scoped = await ltm_facade.search(
        "Nebula Gate codename",
        top_k=5,
        conversation_id="session-bob",
    )
    # Alice-scoped search should see Alice content when indexed.
    if alice_hits:
        assert any("Nebula" in h.get("content", "") for h in alice_hits)
    # Bob-scoped must not return Alice-only messages.
    assert not any("Nebula" in h.get("content", "") for h in bob_scoped)

    # LTM fact is available from any conversation via get_relevant_context.
    ctx = await ltm_facade.get_relevant_context("deploy timezone for production", top_k=3)
    assert any(
        "Moscow" in r.get("content", "") or "timezone" in r.get("content", "").lower()
        for r in ctx["semantic"]
    )


@pytest.mark.asyncio
async def test_forget_clears_conversation_not_ltm(ltm_facade):
    """/forget wipes STM for the session; semantic LTM facts remain."""
    from cli.shared.commands.forget_memory import wipe_conversation_memory_for_host

    conv_id = "forget-ltm-session"
    await ltm_facade.save_message(
        conv_id,
        "user",
        "Remember that the API base URL is https://api.example.internal/v2",
    )
    await ltm_facade.store_fact(
        "api_base",
        "API base URL is https://api.example.internal/v2",
        source=conv_id,
    )

    host = SimpleNamespace(
        conversation_id=conv_id,
        agent=SimpleNamespace(
            memory=ltm_facade,
            context_manager=SimpleNamespace(invalidate_usage_cache=lambda _cid: None),
        ),
    )
    assert await wipe_conversation_memory_for_host(host) is True
    assert await ltm_facade.get_conversation(conv_id, limit=20) == []

    fact = await ltm_facade.get_fact("api_base")
    assert fact is not None
    assert "api.example.internal" in fact["content"]

    ctx = await ltm_facade.get_relevant_context("what is the API base URL?", top_k=3)
    assert any("api.example.internal" in r.get("content", "") for r in ctx["semantic"])


# ---------------------------------------------------------------------------
# memory_retrieval_node — graph injection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_retrieval_node_injects_ltm_and_conversation(ltm_facade):
    """Graph first node surfaces semantic + conversation hits for user_input."""
    from core.domain.graph_runtime import GraphRuntime
    from core.graph.nodes.memory_retrieval_node import memory_retrieval_node

    await ltm_facade.store_fact(
        "gateway_port",
        "Holix gateway listens on port 8741 by default",
        source="docs",
    )
    await ltm_facade.save_message(
        "graph-conv-1",
        "user",
        "We configured the local gateway port to 8741 for Studio",
    )
    await ltm_facade.store_strategy(
        "prefer_graph",
        "Prefer ReAct mode for simple Q&A",
        category="execution_mode",
    )

    agent = SimpleNamespace(memory=ltm_facade, agent_slot="main")
    runtime = GraphRuntime(
        client=SimpleNamespace(),
        model="test-model",
        config=SimpleNamespace(),
        memory=ltm_facade,
        tools=SimpleNamespace(),
        skills=SimpleNamespace(),
        context_manager=SimpleNamespace(),
        events=SimpleNamespace(),
        agent=agent,
    )
    state = {
        "user_input": "What port does the gateway use?",
        "conversation_id": "graph-conv-1",
        "messages": [],
    }
    config = {"configurable": {"_runtime": runtime, "_agent": agent}}

    update = await memory_retrieval_node(state, config)

    memories = update.get("relevant_memories") or []
    strategies = update.get("relevant_strategies") or []
    assert memories, "expected relevant_memories from LTM and/or conversation"

    types = {m.get("type") for m in memories}
    # At least semantic LTM should appear; conversation may also hit.
    assert "semantic" in types or any("8741" in (m.get("content") or "") for m in memories)
    assert any("8741" in (m.get("content") or "") for m in memories)
    assert strategies or update.get("relevant_skills") is not None


@pytest.mark.asyncio
async def test_memory_retrieval_node_without_agent_is_empty():
    """No agent in config → empty memory fields (no crash)."""
    from core.graph.nodes.memory_retrieval_node import memory_retrieval_node

    update = await memory_retrieval_node(
        {"user_input": "anything", "conversation_id": "x"},
        {"configurable": {}},
    )
    assert update["relevant_memories"] == []
    assert update["relevant_skills"] == []
    assert update["relevant_strategies"] == []


# ---------------------------------------------------------------------------
# Profile isolation (not project / not system-global)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ltm_isolated_across_profiles(temp_dir):
    """Two profile data roots do not share LTM facts or conversation search."""
    base = Path(temp_dir)
    alice_root = base / "profiles" / "alice" / "data" / "memory"
    bob_root = base / "profiles" / "bob" / "data" / "memory"
    alice_root.mkdir(parents=True)
    bob_root.mkdir(parents=True)

    alice = _make_facade(alice_root, collection="alice_mem")
    bob = _make_facade(bob_root, collection="bob_mem")
    await alice.initialize_db()
    await bob.initialize_db()

    await alice.store_fact(
        "owner",
        "Alice profile secret: project Phoenix uses Rust",
        source="alice",
    )
    await alice.save_message(
        "a1",
        "user",
        "Alice only conversation about Phoenix Rust rewrite",
    )
    await bob.store_fact(
        "owner",
        "Bob profile secret: project Orion uses Go",
        source="bob",
    )

    alice_fact = await alice.get_fact("owner")
    bob_fact = await bob.get_fact("owner")
    assert alice_fact is not None and "Phoenix" in alice_fact["content"]
    assert bob_fact is not None and "Orion" in bob_fact["content"]
    assert "Phoenix" not in bob_fact["content"]
    assert "Orion" not in alice_fact["content"]

    alice_ctx = await alice.get_relevant_context("Phoenix Rust project", top_k=3)
    bob_ctx = await bob.get_relevant_context("Phoenix Rust project", top_k=3)
    alice_blob = " ".join(r.get("content", "") for r in alice_ctx["semantic"])
    bob_blob = " ".join(r.get("content", "") for r in bob_ctx["semantic"])
    assert "Phoenix" in alice_blob or "Rust" in alice_blob
    # Bob must not surface Alice's exclusive fact.
    assert "Phoenix" not in bob_blob


def test_memory_paths_live_under_profile_not_project(temp_dir, monkeypatch):
    """Profile service places memory under profile data/, not workspace/.holix."""
    from core.profile.service import ProfileConfig, resolve_profile_storage_paths

    holix_home = Path(temp_dir) / "holix_home"
    holix_home.mkdir()
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))

    profile_dir = holix_home / "profiles" / "demo"
    profile_dir.mkdir(parents=True)
    resolved = resolve_profile_storage_paths(
        "demo",
        ProfileConfig(profile_name="demo"),
        profile_dir=profile_dir,
    )

    memory_db = Path(resolved.memory_db_path)
    ltm_db = Path(resolved.ltm_db_path)
    vector_db = Path(resolved.vector_db_path)
    workspace = Path(resolved.workspace_root)

    assert memory_db.name == "memory.db"
    assert "data" in memory_db.parts
    assert "memory" in memory_db.parts
    assert str(profile_dir) in str(memory_db)
    assert ltm_db.parent == memory_db.parent
    assert ltm_db.name == "ltm.db"
    assert "memory" in vector_db.parts
    # Memory must not live under the workspace tree (not per-project .holix).
    with pytest.raises(ValueError):
        memory_db.resolve().relative_to(workspace.resolve())
    assert workspace.name == "workspace"


@pytest.mark.asyncio
async def test_ltm_disabled_returns_empty_context(temp_dir, request):
    """With enable_long_term_memory=False, context API is empty and stores raise."""
    root = Path(temp_dir)
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        memory_db_path=str(root / "m.db"),
        vector_db_path=str(root / "v"),
        ltm_db_path=str(root / "l.db"),
        memory_chroma_collection=_unique_collection(request),
        enable_long_term_memory=False,
    )
    facade = MemoryFacade(cfg)
    await facade.initialize_db()

    await facade.save_message("c", "user", "still stores conversation")
    ctx = await facade.get_relevant_context("anything")
    assert ctx == {"episodic": [], "semantic": [], "strategic": []}
    with pytest.raises(RuntimeError, match="Long-term memory is disabled"):
        await facade.store_fact("k", "v")
