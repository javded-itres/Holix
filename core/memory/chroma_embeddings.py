"""Shared ChromaDB embedding function."""

from __future__ import annotations

import sys
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chromadb.api.types import EmbeddingFunction


def _preferred_onnx_providers() -> list[str]:
    try:
        import onnxruntime as ort
    except ImportError:
        return ["CPUExecutionProvider"]

    available = set(ort.get_available_providers())
    if sys.platform == "darwin":
        # ChromaDB removes CoreML anyway; CPU is stable on Apple Silicon.
        order = ["CPUExecutionProvider"]
    elif "CUDAExecutionProvider" in available:
        order = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    else:
        order = ["CPUExecutionProvider"]
    picked = [provider for provider in order if provider in available]
    return picked or list(available)


@lru_cache(maxsize=1)
def default_embedding_function() -> EmbeddingFunction:
    """Singleton ONNX embedder with explicit providers (no ChromaDB warning spam)."""
    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

    return ONNXMiniLM_L6_V2(preferred_providers=_preferred_onnx_providers())


def get_or_create_collection(client: Any, *, name: str, metadata: dict[str, str]) -> Any:
    """Open an existing collection or create one with the shared embedder."""
    try:
        return client.get_collection(name)
    except Exception:
        return client.create_collection(
            name=name,
            metadata=metadata,
            embedding_function=default_embedding_function(),
        )