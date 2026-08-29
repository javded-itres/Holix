"""pgvector backend (skipped unless a Postgres DSN is available)."""

from __future__ import annotations

import os
import uuid

import pytest
from core.di.runtime_config import HolixRuntimeConfig
from core.memory.vector_backend import hash_embedder, is_postgres_dsn, open_vector_backend


def _dsn() -> str:
    return (
        os.environ.get("HOLIX_VECTOR_TEST_DSN")
        or os.environ.get("HOLIX_VECTOR_DSN")
        or os.environ.get("STUDIO_DATABASE_URL")
        or ""
    ).strip()


_PG_DSN = _dsn()

pytestmark = pytest.mark.skipif(
    not is_postgres_dsn(_PG_DSN),
    reason="Postgres DSN not set (HOLIX_VECTOR_TEST_DSN / STUDIO_DATABASE_URL)",
)


def test_pgvector_roundtrip() -> None:
    table = "holix_vectors_test_" + uuid.uuid4().hex[:10]
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        vector_backend="pgvector",
        vector_dsn=_PG_DSN,
        vector_dim=8,
        vector_table=table,
        profile_name="pgvector_test",
    )
    backend = open_vector_backend(cfg, embedder=hash_embedder(8))
    coll = backend.get_collection("memory")
    coll.upsert(
        documents=["alpha vector row", "beta something else"],
        ids=["1", "2"],
        metadatas=[{"conversation_id": "c1"}, {"conversation_id": "c2"}],
    )
    hits = coll.query(["alpha vector"], n_results=1)
    assert hits["ids"][0][0] == "1"
    scoped = coll.query(["alpha"], n_results=5, where={"conversation_id": "c2"})
    assert scoped["ids"][0] == ["2"]
    coll.delete(ids=["2"])
    assert coll.count() == 1
    coll.delete(where={"conversation_id": "c1"})
    assert coll.count() == 0
