"""Chroma PersistentClient backend (default for local Holix)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.memory.chroma_client import get_persistent_client
from core.memory.chroma_embeddings import get_or_create_collection
from core.paths import prepare_vector_db_dir


class ChromaVectorBackend:
    def __init__(self, path: str | Path) -> None:
        self._path = prepare_vector_db_dir(path)
        self.chroma_client = get_persistent_client(self._path)
        self._collections: dict[str, Any] = {}

    def get_collection(self, name: str) -> Any:
        key = str(name or "memory")
        coll = self._collections.get(key)
        if coll is None:
            coll = get_or_create_collection(
                self.chroma_client,
                name=key,
                metadata={"hnsw:space": "cosine"},
            )
            self._collections[key] = coll
        return coll
