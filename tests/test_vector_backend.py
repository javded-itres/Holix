"""Vector backend factory and in-memory store."""

from __future__ import annotations

import pytest
from core.di.runtime_config import HolixRuntimeConfig
from core.memory.conversation import ConversationStore
from core.memory.vector import VectorMemoryStore
from core.memory.vector_backend import (
    hash_embedder,
    normalize_vector_backend,
    open_vector_backend,
    uses_on_disk_chroma,
)


def test_normalize_vector_backend() -> None:
    assert normalize_vector_backend(None) == "chroma"
    assert normalize_vector_backend("Chroma") == "chroma"
    assert normalize_vector_backend("pgvector") == "pgvector"
    assert normalize_vector_backend("postgres") == "pgvector"
    assert normalize_vector_backend("memory") == "memory"


def test_uses_on_disk_chroma_from_config() -> None:
    cfg = HolixRuntimeConfig.from_settings().with_overrides(vector_backend="pgvector")
    assert uses_on_disk_chroma(cfg) is False
    cfg = HolixRuntimeConfig.from_settings().with_overrides(vector_backend="chroma")
    assert uses_on_disk_chroma(cfg) is True


def test_memory_backend_upsert_query_delete() -> None:
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        vector_backend="memory",
        vector_dim=8,
        profile_name="vec_test",
    )
    backend = open_vector_backend(cfg, embedder=hash_embedder(8))
    coll = backend.get_collection("memory")
    coll.upsert(
        documents=["Postgres vector search", "unrelated cooking recipe"],
        ids=["a", "b"],
        metadatas=[{"conversation_id": "c1"}, {"conversation_id": "c2"}],
    )
    hits = coll.query(["Postgres vector search"], n_results=1)
    assert hits["ids"][0][0] == "a"
    filtered = coll.query(
        ["unrelated cooking recipe"],
        n_results=5,
        where={"conversation_id": "c2"},
    )
    assert filtered["ids"][0] == ["b"]
    coll.delete(where={"conversation_id": "c1"})
    assert coll.count() == 1


@pytest.mark.asyncio
async def test_conversation_store_memory_backend_search(tmp_path) -> None:
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        memory_db_path=str(tmp_path / "mem.db"),
        vector_db_path=str(tmp_path / "vec"),
        vector_backend="memory",
        vector_dim=8,
        memory_chroma_collection="test_memory",
    )
    store = ConversationStore(cfg)
    await store.initialize_db()
    await store.save_message("c1", "user", "Holix agent should use pgvector on Studio")
    hits = await store.search("anything", top_k=2, conversation_id="c1")
    assert len(hits) == 1
    assert "pgvector" in hits[0]["content"]


def test_ltm_vector_store_memory_backend(tmp_path) -> None:
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        vector_db_path=str(tmp_path / "vec"),
        vector_backend="memory",
        vector_dim=8,
        ltm_db_path=str(tmp_path / "ltm.db"),
    )
    store = VectorMemoryStore(config=cfg)
    store.upsert("ltm_semantic", ["Studio uses PostgreSQL"], ["s1"], [{"k": "v"}])
    found = store.query("ltm_semantic", ["Studio uses PostgreSQL"], n_results=1)
    assert found["documents"][0][0] == "Studio uses PostgreSQL"


def test_pgvector_requires_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOLIX_VECTOR_DSN", raising=False)
    monkeypatch.delenv("HOLIX_VECTOR_DATABASE_URL", raising=False)
    monkeypatch.delenv("VECTOR_DSN", raising=False)
    monkeypatch.delenv("STUDIO_DATABASE_URL", raising=False)
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        vector_backend="pgvector",
        vector_dsn="",
    )
    with pytest.raises(RuntimeError, match="HOLIX_VECTOR_DSN"):
        open_vector_backend(cfg)
