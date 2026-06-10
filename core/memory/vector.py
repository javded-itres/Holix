"""
Vector Memory Store for Helix Long-term Memory.

Thin wrapper around ChromaDB managing multiple collections for typed memory:
- ltm_episodic: episode summaries from past conversations
- ltm_semantic: facts and knowledge entries
- ltm_strategic: strategies and preferences

Provides a unified search API across all collections.
"""

import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from core.memory.chroma_embeddings import get_or_create_collection

logger = logging.getLogger(__name__)


class VectorMemoryStore:
    """Manages ChromaDB collections for long-term memory types.

    Each memory type gets its own collection for clean separation
    and type-specific retrieval. Collections are created lazily
    on first write to minimize initialization overhead.
    """

    def __init__(self, vector_db_path: str | None = None):
        if vector_db_path is None:
            from core.di.runtime_config import HelixRuntimeConfig
            vector_db_path = HelixRuntimeConfig.from_settings().vector_db_path
        self._vector_db_path = Path(vector_db_path)
        self._vector_db_path.mkdir(parents=True, exist_ok=True)

        self._chroma_client = chromadb.PersistentClient(
            path=str(self._vector_db_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # Lazy collection cache — created on first access
        self._collections: dict[str, chromadb.Collection] = {}

    def _get_collection(self, name: str) -> chromadb.Collection:
        """Get or create a ChromaDB collection by name.

        Collections are created lazily on first access to avoid
        unnecessary disk usage when a memory type is not used.
        """
        if name not in self._collections:
            self._collections[name] = get_or_create_collection(
                self._chroma_client,
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[name]

    @property
    def episodic(self) -> chromadb.Collection:
        """Episodic memory collection (conversation summaries)."""
        return self._get_collection("ltm_episodic")

    @property
    def semantic(self) -> chromadb.Collection:
        """Semantic memory collection (facts and knowledge)."""
        return self._get_collection("ltm_semantic")

    @property
    def strategic(self) -> chromadb.Collection:
        """Strategic memory collection (strategies and preferences)."""
        return self._get_collection("ltm_strategic")

    def add(
        self,
        collection_name: str,
        documents: list[str],
        ids: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        """Add documents to a collection.

        Args:
            collection_name: Name of the collection.
            documents: List of document strings.
            ids: List of unique IDs.
            metadatas: Optional list of metadata dicts.
        """
        collection = self._get_collection(collection_name)
        try:
            collection.add(
                documents=documents,
                ids=ids,
                metadatas=metadatas,
            )
        except chromadb.errors.IDAlreadyExistsError:
            # Upsert semantics: if ID exists, update instead
            collection.upsert(
                documents=documents,
                ids=ids,
                metadatas=metadatas,
            )
        except Exception as e:
            logger.warning(f"Failed to add to {collection_name}: {e}")

    def upsert(
        self,
        collection_name: str,
        documents: list[str],
        ids: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        """Upsert documents into a collection (insert or update).

        Args:
            collection_name: Name of the collection.
            documents: List of document strings.
            ids: List of unique IDs.
            metadatas: Optional list of metadata dicts.
        """
        collection = self._get_collection(collection_name)
        try:
            collection.upsert(
                documents=documents,
                ids=ids,
                metadatas=metadatas,
            )
        except Exception as e:
            logger.warning(f"Failed to upsert to {collection_name}: {e}")

    def query(
        self,
        collection_name: str,
        query_texts: list[str],
        n_results: int = 8,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Semantic search in a specific collection.

        Args:
            collection_name: Name of the collection.
            query_texts: List of query strings.
            n_results: Number of results per query.
            where: Optional metadata filter.

        Returns:
            ChromaDB query results dict.
        """
        collection = self._get_collection(collection_name)
        try:
            return collection.query(
                query_texts=query_texts,
                n_results=n_results,
                where=where,
            )
        except Exception as e:
            logger.warning(f"Failed to query {collection_name}: {e}")
            return {"documents": [[]], "metadatas": [[]], "distances": [[]], "ids": [[]]}

    def delete(
        self,
        collection_name: str,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> None:
        """Delete documents from a collection.

        Args:
            collection_name: Name of the collection.
            ids: Optional list of IDs to delete.
            where: Optional metadata filter for deletion.
        """
        collection = self._get_collection(collection_name)
        try:
            if ids:
                collection.delete(ids=ids)
            elif where:
                collection.delete(where=where)
        except Exception as e:
            logger.warning(f"Failed to delete from {collection_name}: {e}")

    def search_all(
        self,
        query: str,
        top_k: int = 5,
        collection_names: list[str] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Search across multiple collections and return categorized results.

        Args:
            query: Search query string.
            top_k: Number of results per collection.
            collection_names: Optional list of collections to search.
                             Defaults to all LTM collections.

        Returns:
            Dict mapping collection names to lists of result dicts,
            each with 'content', 'metadata', and 'distance' keys.
        """
        if collection_names is None:
            collection_names = ["ltm_episodic", "ltm_semantic", "ltm_strategic"]

        results: dict[str, list[dict[str, Any]]] = {}

        for name in collection_names:
            raw = self.query(name, [query], n_results=top_k)
            items: list[dict[str, Any]] = []

            if raw["documents"] and raw["documents"][0]:
                for i, doc in enumerate(raw["documents"][0]):
                    items.append({
                        "content": doc,
                        "metadata": raw["metadatas"][0][i] if raw["metadatas"] else {},
                        "distance": raw["distances"][0][i] if raw.get("distances") else None,
                    })

            results[name] = items

        return results

    def get_stats(self) -> dict[str, int]:
        """Get document counts for all LTM collections.

        Returns:
            Dict mapping collection names to document counts.
        """
        stats = {}
        for name in ["ltm_episodic", "ltm_semantic", "ltm_strategic"]:
            try:
                collection = self._get_collection(name)
                stats[name] = collection.count()
            except Exception:
                stats[name] = 0
        return stats