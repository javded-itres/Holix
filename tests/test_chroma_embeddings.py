"""ChromaDB embedding helper."""

from __future__ import annotations

import sys

from core.memory.chroma_embeddings import (
    _preferred_onnx_providers,
    default_embedding_function,
    get_or_create_collection,
)


def test_default_embedding_function_is_singleton() -> None:
    first = default_embedding_function()
    second = default_embedding_function()
    assert first is second
    assert first._preferred_providers
    assert "CPUExecutionProvider" in first._preferred_providers


def test_darwin_onnx_providers_are_cpu_only() -> None:
    if sys.platform != "darwin":
        providers = _preferred_onnx_providers()
        assert providers
        return
    assert _preferred_onnx_providers() == ["CPUExecutionProvider"]


def test_get_or_create_collection_passes_cpu_embedder() -> None:
    captured: dict[str, object] = {}

    class _Client:
        def get_collection(self, name, embedding_function=None, **_kwargs):
            captured["name"] = name
            captured["embedding_function"] = embedding_function
            return {"name": name}

        def create_collection(self, **_kwargs):
            raise AssertionError("must reuse existing collection")

    collection = get_or_create_collection(_Client(), name="ltm_semantic", metadata={})
    assert collection == {"name": "ltm_semantic"}
    assert captured["embedding_function"] is default_embedding_function()
    assert "CPUExecutionProvider" in captured["embedding_function"]._preferred_providers
