"""Vector collection contract shared by Chroma, pgvector, and in-memory backends."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


def empty_query_result() -> dict[str, Any]:
    return {"documents": [[]], "metadatas": [[]], "distances": [[]], "ids": [[]]}


def metadata_matches(meta: dict[str, Any] | None, where: dict[str, Any] | None) -> bool:
    if not where:
        return True
    data = meta or {}
    for key, expected in where.items():
        if str(key).startswith("$"):
            continue
        if data.get(key) != expected:
            return False
    return True


@runtime_checkable
class VectorCollection(Protocol):
    def add(
        self,
        documents: list[str],
        ids: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None: ...

    def upsert(
        self,
        documents: list[str],
        ids: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None: ...

    def query(
        self,
        query_texts: list[str],
        n_results: int = 8,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def delete(
        self,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> None: ...

    def count(self) -> int: ...


@runtime_checkable
class VectorBackend(Protocol):
    chroma_client: Any

    def get_collection(self, name: str) -> VectorCollection: ...
