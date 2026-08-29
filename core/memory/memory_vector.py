"""In-memory vector backend (tests / HOLIX_VECTOR_BACKEND=memory)."""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from typing import Any

from core.memory.vector_protocol import empty_query_result, metadata_matches

Embedder = Callable[[list[str]], list[list[float]]]


def _cosine_distance(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 1.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 1.0
    sim = max(-1.0, min(1.0, dot / (na * nb)))
    return 1.0 - sim


class InMemoryVectorCollection:
    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self._lock = threading.RLock()
        self._docs: dict[str, tuple[str, dict[str, Any], list[float]]] = {}

    def add(
        self,
        documents: list[str],
        ids: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        self.upsert(documents, ids, metadatas)

    def upsert(
        self,
        documents: list[str],
        ids: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        if not documents:
            return
        vectors = self._embedder(list(documents))
        with self._lock:
            for i, doc_id in enumerate(ids):
                meta = dict(metadatas[i]) if metadatas and i < len(metadatas) else {}
                vec = list(vectors[i]) if i < len(vectors) else []
                self._docs[str(doc_id)] = (documents[i], meta, vec)

    def query(
        self,
        query_texts: list[str],
        n_results: int = 8,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not query_texts or n_results <= 0:
            return empty_query_result()
        qvec = self._embedder([query_texts[0]])[0]
        scored: list[tuple[float, str, str, dict[str, Any]]] = []
        with self._lock:
            items = list(self._docs.items())
        for doc_id, (text, meta, vec) in items:
            if not metadata_matches(meta, where):
                continue
            scored.append((_cosine_distance(qvec, vec), doc_id, text, meta))
        scored.sort(key=lambda row: row[0])
        top = scored[:n_results]
        return {
            "ids": [[row[1] for row in top]],
            "documents": [[row[2] for row in top]],
            "metadatas": [[row[3] for row in top]],
            "distances": [[row[0] for row in top]],
        }

    def delete(
        self,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            if ids:
                for doc_id in ids:
                    self._docs.pop(str(doc_id), None)
                return
            if where:
                drop = [
                    key
                    for key, (_text, meta, _vec) in self._docs.items()
                    if metadata_matches(meta, where)
                ]
                for key in drop:
                    self._docs.pop(key, None)

    def count(self) -> int:
        with self._lock:
            return len(self._docs)


class InMemoryVectorBackend:
    chroma_client = None

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self._collections: dict[str, InMemoryVectorCollection] = {}
        self._lock = threading.Lock()

    def get_collection(self, name: str) -> InMemoryVectorCollection:
        key = str(name or "default")
        with self._lock:
            coll = self._collections.get(key)
            if coll is None:
                coll = InMemoryVectorCollection(self._embedder)
                self._collections[key] = coll
            return coll
