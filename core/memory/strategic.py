"""
Strategic Memory Store for Helix Long-term Memory.

Stores high-level patterns, preferences, and strategies.
This is the smallest but highest-impact memory type:
- Preferred approaches for task types
- User preferences and working patterns
- Recurring failure modes to avoid
- Mode/routing preferences from past experience

Created by the Meta-Agent or explicitly by the user.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiosqlite

from core.memory.vector import VectorMemoryStore

logger = logging.getLogger(__name__)


class StrategicMemoryStore:
    """Manages strategic memory — strategies, preferences, and patterns.

    Strategic entries are high-level heuristics that guide agent behavior.
    They are small in number but high in impact. Examples:
    - "user_prefers_async_code" → always generate async Python
    - "coding_tasks_use_hybrid_mode" → for code tasks, prefer hybrid execution
    - "avoid_sqlite_for_large_datasets" → known failure mode
    """

    def __init__(self, db_path: str, vector_store: VectorMemoryStore):
        self._db_path = db_path
        self._vector_store = vector_store

    async def store_strategy(
        self,
        key: str,
        content: str,
        category: str = "general",
        source: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Store or update a strategic memory entry.

        Uses upsert semantics: if a strategy with this key already exists,
        it is updated with the new content.

        Args:
            key: Unique identifier (e.g., "user_prefers_async_code").
            content: Strategy description / value.
            category: Grouping category (e.g., "user_preference", "execution_mode", "failure_mode").
            source: Where this strategy came from.
            metadata: Optional additional metadata.

        Returns:
            Row ID in ltm_entries table.
        """
        meta = metadata or {}
        meta["source"] = source
        meta["category"] = category
        meta["timestamp"] = datetime.now().isoformat()

        async with aiosqlite.connect(self._db_path) as db:
            # Check if key already exists
            cursor = await db.execute(
                "SELECT id FROM ltm_entries WHERE memory_type = 'strategic' AND key = ?",
                (key,),
            )
            existing = await cursor.fetchone()

            if existing:
                # Update existing entry
                await db.execute(
                    """UPDATE ltm_entries
                       SET content = ?, source = ?, category = ?, metadata = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (content, source, category, json.dumps(meta), existing[0]),
                )
                entry_id = existing[0]
            else:
                # Insert new entry
                cursor = await db.execute(
                    """INSERT INTO ltm_entries (memory_type, key, content, source, category, metadata)
                       VALUES ('strategic', ?, ?, ?, ?, ?)""",
                    (key, content, source, category, json.dumps(meta)),
                )
                entry_id = cursor.lastrowid

            await db.commit()

        # Upsert in vector store
        self._vector_store.upsert(
            collection_name="ltm_strategic",
            documents=[f"{key}: {content}"],
            ids=[f"strategic_{key}"],
            metadatas=[{"key": key, "category": category, **meta}],
        )

        return entry_id

    async def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Semantic search across strategic memories.

        Args:
            query: Search query.
            top_k: Number of results.

        Returns:
            List of matching strategies.
        """
        results = self._vector_store.query(
            "ltm_strategic", [query], n_results=top_k
        )

        strategies = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results.get("distances") else None
                strategies.append({
                    "key": meta.get("key", ""),
                    "content": doc,
                    "category": meta.get("category", "general"),
                    "metadata": meta,
                    "distance": distance,
                })

        return strategies

    async def get_strategies_for_category(
        self,
        category: str,
    ) -> List[Dict[str, Any]]:
        """Get all strategies in a specific category.

        Args:
            category: Category to filter by (e.g., "user_preference", "execution_mode").

        Returns:
            List of strategy dicts in that category.
        """
        strategies = []
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT id, key, content, source, metadata, created_at, updated_at
                   FROM ltm_entries
                   WHERE memory_type = 'strategic' AND category = ?
                   ORDER BY updated_at DESC""",
                (category,),
            )
            rows = await cursor.fetchall()
            for row in rows:
                meta = {}
                if row["metadata"]:
                    try:
                        meta = json.loads(row["metadata"])
                    except json.JSONDecodeError:
                        pass
                strategies.append({
                    "id": row["id"],
                    "key": row["key"],
                    "content": row["content"],
                    "source": row["source"],
                    "metadata": meta,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                })

        return strategies

    async def get_all_strategies(self) -> List[Dict[str, Any]]:
        """Get all stored strategies (for prompt injection).

        Strategic memory is small and high-value, so injecting
        all of it into the prompt is usually acceptable.

        Returns:
            List of all strategy dicts.
        """
        strategies = []
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT key, content, category, source, metadata
                   FROM ltm_entries
                   WHERE memory_type = 'strategic'
                   ORDER BY category, updated_at DESC""",
            )
            rows = await cursor.fetchall()
            for row in rows:
                meta = {}
                if row["metadata"]:
                    try:
                        meta = json.loads(row["metadata"])
                    except json.JSONDecodeError:
                        pass
                strategies.append({
                    "key": row["key"],
                    "content": row["content"],
                    "category": row["category"],
                    "source": row["source"],
                    "metadata": meta,
                })

        return strategies

    async def delete_strategy(self, key: str) -> bool:
        """Delete a strategy by its key.

        Args:
            key: Unique strategy identifier.

        Returns:
            True if the strategy was deleted.
        """
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM ltm_entries WHERE memory_type = 'strategic' AND key = ?",
                (key,),
            )
            await db.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            self._vector_store.delete(
                collection_name="ltm_strategic",
                ids=[f"strategic_{key}"],
            )

        return deleted

    def format_strategies_for_prompt(
        self,
        strategies: List[Dict[str, Any]],
    ) -> str:
        """Format strategies for inclusion in the system prompt.

        Args:
            strategies: List of strategy dicts.

        Returns:
            Formatted string for prompt injection.
        """
        if not strategies:
            return ""

        # Group by category
        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for s in strategies:
            cat = s.get("category", "general")
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(s)

        parts = ["## Strategic Memory\n"]
        category_labels = {
            "user_preference": "User Preferences",
            "execution_mode": "Execution Mode Preferences",
            "failure_mode": "Known Failure Modes (Avoid)",
            "general": "General Strategies",
        }

        for cat, items in by_category.items():
            label = category_labels.get(cat, cat.replace("_", " ").title())
            parts.append(f"### {label}\n")
            for item in items:
                key = item.get("key", "")
                content = item.get("content", "")
                # Clean up the content (remove the "key: " prefix if present)
                clean_content = content
                if content.startswith(f"{key}: "):
                    clean_content = content[len(key) + 2:]
                parts.append(f"- **{key}**: {clean_content}")
            parts.append("")

        return "\n".join(parts)