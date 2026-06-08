"""Embedding storage for docs chat retrieval."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def _embedding_text(chunk: dict[str, Any]) -> str:
    keywords = " ".join(chunk.get("keywords") or [])
    return "\n".join(
        [
            chunk.get("title") or "",
            chunk.get("heading") or "",
            keywords,
            chunk.get("body") or "",
        ]
    ).strip()


def embed_chunks(chunks: list[dict[str, Any]]) -> np.ndarray:
    from core.memory.chroma_embeddings import default_embedding_function

    texts = [_embedding_text(chunk) for chunk in chunks]
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    vectors = default_embedding_function()(texts)
    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def save_vectors(path: Path, *, chunk_ids: list[str], vectors: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, ids=np.asarray(chunk_ids, dtype=object), embeddings=vectors)


def load_vectors(path: Path) -> tuple[list[str], np.ndarray] | None:
    if not path.is_file():
        return None
    try:
        data = np.load(path, allow_pickle=True)
        ids = [str(x) for x in data["ids"].tolist()]
        vectors = np.asarray(data["embeddings"], dtype=np.float32)
        return ids, vectors
    except (OSError, KeyError, ValueError) as exc:
        logger.warning("docs chat: could not load vectors: %s", exc)
        return None


def embed_query(query: str) -> np.ndarray | None:
    try:
        from core.memory.chroma_embeddings import default_embedding_function

        vector = np.asarray(default_embedding_function()([query]), dtype=np.float32)[0]
        norm = np.linalg.norm(vector)
        if norm == 0:
            return None
        return vector / norm
    except Exception as exc:
        logger.warning("docs chat: query embedding failed: %s", exc)
        return None


def save_manifest(path: Path, *, model: str, dim: int, count: int) -> None:
    path.write_text(
        json.dumps({"model": model, "dim": dim, "count": count}, indent=2),
        encoding="utf-8",
    )