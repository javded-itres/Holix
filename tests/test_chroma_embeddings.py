"""ChromaDB embedding helper."""

from __future__ import annotations

from core.memory.chroma_embeddings import default_embedding_function


def test_default_embedding_function_is_singleton() -> None:
    first = default_embedding_function()
    second = default_embedding_function()
    assert first is second
    assert first._preferred_providers
    assert "CPUExecutionProvider" in first._preferred_providers