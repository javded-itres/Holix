"""
Semantic Memory Store for Helix Long-term Memory.

Stores facts, concepts, and learned knowledge as key-value entries
with rich metadata. This is the "knowledge base" layer — structured
information the agent has discovered or been told.
"""

import json
import logging
from datetime import datetime
from typing import Any

import aiosqlite

from core.memory.vector import VectorMemoryStore

logger = logging.getLogger(__name__)


class SemanticMemoryStore:
    """Manages semantic memory — facts and knowledge entries.

    Each fact has a unique key (for exact lookup) and is indexed
    in ChromaDB for semantic search. Facts can be updated (upsert)
    when new information supersedes old.
    """

    def __init__(self, db_path: str, vector_store: VectorMemoryStore):
        self._db_path = db_path
        self._vector_store = vector_store

    async def store_fact(
        self,
        key: str,
        content: str,
        source: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Store or update a semantic fact.

        Uses upsert semantics: if a fact with this key already exists,
        it is updated with the new content and metadata.

        Args:
            key: Unique identifier for the fact (e.g., "project_uses_fastapi").
            content: The fact content / value.
            source: Where this fact came from (conversation_id, 'user', etc.).
            metadata: Optional additional metadata.

        Returns:
            Row ID in ltm_entries table.
        """
        meta = metadata or {}
        meta["source"] = source
        meta["timestamp"] = datetime.now().isoformat()

        async with aiosqlite.connect(self._db_path) as db:
            # Check if key already exists
            cursor = await db.execute(
                "SELECT id FROM ltm_entries WHERE memory_type = 'semantic' AND key = ?",
                (key,),
            )
            existing = await cursor.fetchone()

            if existing:
                # Update existing entry
                await db.execute(
                    """UPDATE ltm_entries
                       SET content = ?, source = ?, metadata = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (content, source, json.dumps(meta), existing[0]),
                )
                entry_id = existing[0]
            else:
                # Insert new entry
                cursor = await db.execute(
                    """INSERT INTO ltm_entries (memory_type, key, content, source, category, metadata)
                       VALUES ('semantic', ?, ?, ?, 'fact', ?)""",
                    (key, content, source, json.dumps(meta)),
                )
                entry_id = cursor.lastrowid

            await db.commit()

        # Upsert in vector store
        self._vector_store.upsert(
            collection_name="ltm_semantic",
            documents=[f"{key}: {content}"],  # Include key in document for better search
            ids=[f"semantic_{key}"],
            metadatas=[{"key": key, **meta}],
        )

        return entry_id

    async def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Semantic search across stored facts.

        Args:
            query: Search query.
            top_k: Number of results.

        Returns:
            List of matching facts with key, content, metadata, distance.
        """
        results = self._vector_store.query(
            "ltm_semantic", [query], n_results=top_k
        )

        facts = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results.get("distances") else None
                facts.append({
                    "key": meta.get("key", ""),
                    "content": doc,
                    "metadata": meta,
                    "distance": distance,
                })

        return facts

    async def get_fact(self, key: str) -> dict[str, Any] | None:
        """Get a specific fact by its key.

        Args:
            key: Unique fact identifier.

        Returns:
            Fact dict with key, content, metadata, or None if not found.
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT id, key, content, source, metadata, created_at, updated_at
                   FROM ltm_entries
                   WHERE memory_type = 'semantic' AND key = ?""",
                (key,),
            )
            row = await cursor.fetchone()

            if not row:
                return None

            meta = {}
            if row["metadata"]:
                try:
                    meta = json.loads(row["metadata"])
                except json.JSONDecodeError:
                    pass

            return {
                "id": row["id"],
                "key": row["key"],
                "content": row["content"],
                "source": row["source"],
                "metadata": meta,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

    async def get_all_facts(self) -> list[dict[str, Any]]:
        """Get all stored facts (for prompt injection).

        Returns:
            List of all fact dicts.
        """
        facts = []
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT key, content, source, metadata
                   FROM ltm_entries
                   WHERE memory_type = 'semantic'
                   ORDER BY updated_at DESC""",
            )
            rows = await cursor.fetchall()
            for row in rows:
                meta = {}
                if row["metadata"]:
                    try:
                        meta = json.loads(row["metadata"])
                    except json.JSONDecodeError:
                        pass
                facts.append({
                    "key": row["key"],
                    "content": row["content"],
                    "source": row["source"],
                    "metadata": meta,
                })

        return facts

    async def delete_fact(self, key: str) -> bool:
        """Delete a fact by its key.

        Args:
            key: Unique fact identifier.

        Returns:
            True if the fact was deleted.
        """
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM ltm_entries WHERE memory_type = 'semantic' AND key = ?",
                (key,),
            )
            await db.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            self._vector_store.delete(
                collection_name="ltm_semantic",
                ids=[f"semantic_{key}"],
            )

        return deleted