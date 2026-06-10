"""Conversation message storage (SQLite + ChromaDB for semantic search)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite
import chromadb
from chromadb.config import Settings as ChromaSettings

from core.di.runtime_config import HelixRuntimeConfig
from core.memory.chroma_embeddings import get_or_create_collection

logger = logging.getLogger(__name__)

_INDEXABLE_ROLES = frozenset({"user", "assistant", "system", "tool"})
_MIN_INDEX_CHARS = 10


class ConversationStore:
    """SQLite + ChromaDB storage for chat messages.

    Contract: ``get_conversation`` returns messages in chronological order (oldest first).
    ``search`` returns results ordered by relevance (ChromaDB distance).
    """

    def __init__(self, config: HelixRuntimeConfig | None = None):
        cfg = config or HelixRuntimeConfig.from_settings()
        self.config = cfg
        self.db_path = Path(cfg.memory_db_path)
        self.vector_db_path = Path(cfg.vector_db_path)

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.vector_db_path.mkdir(parents=True, exist_ok=True)

        self.chroma_client = chromadb.PersistentClient(
            path=str(self.vector_db_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        collection_name = cfg.memory_chroma_collection or "memory"
        self.collection = get_or_create_collection(
            self.chroma_client,
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    async def initialize_db(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversation_id
                ON conversations(conversation_id)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON conversations(timestamp)
            """)
            await db.commit()

    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """INSERT INTO conversations (conversation_id, role, content, metadata)
                   VALUES (?, ?, ?, ?)""",
                (conversation_id, role, content, json.dumps(metadata or {})),
            )
            message_id = cursor.lastrowid
            await db.commit()

        if content and len(content) > _MIN_INDEX_CHARS and role in _INDEXABLE_ROLES:
            try:
                meta = {
                    "conversation_id": conversation_id,
                    "role": role,
                    "timestamp": datetime.now().isoformat(),
                    "message_id": str(message_id),
                }
                if metadata and isinstance(metadata, dict):
                    meta["type"] = metadata.get("type", "")
                    if metadata.get("tool_name"):
                        meta["tool_name"] = str(metadata["tool_name"])

                self.collection.add(
                    documents=[content],
                    metadatas=[meta],
                    ids=[f"{conversation_id}_{message_id}"],
                )
            except Exception as e:
                logger.warning("Failed to add to vector DB: %s", e)

        return message_id

    async def get_conversation(
        self,
        conversation_id: str,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT role, content, timestamp, metadata
                   FROM (
                       SELECT role, content, timestamp, metadata, id
                       FROM conversations
                       WHERE conversation_id = ?
                       ORDER BY id DESC
                       LIMIT ?
                   ) AS recent
                   ORDER BY recent.id ASC""",
                (conversation_id, limit),
            )
            rows = await cursor.fetchall()

            messages = []
            for row in rows:
                msg: dict[str, Any] = {"role": row["role"], "content": row["content"]}
                if row["metadata"]:
                    try:
                        parsed = json.loads(row["metadata"])
                        if parsed:
                            msg["metadata"] = parsed
                    except json.JSONDecodeError:
                        pass
                messages.append(msg)

            return messages

    async def search(
        self,
        query: str,
        top_k: int = 8,
        conversation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            where_filter = {"conversation_id": conversation_id} if conversation_id else None
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter,
            )

            memories = []
            if results["documents"] and results["documents"][0]:
                for i, doc in enumerate(results["documents"][0]):
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    memories.append({
                        "content": doc,
                        "metadata": metadata,
                        "distance": results["distances"][0][i] if results.get("distances") else None,
                    })
            return memories
        except Exception as e:
            logger.warning("Error during semantic search: %s", e)
            return []

    async def replace_conversation_messages(
        self,
        conversation_id: str,
        new_messages: list[dict[str, Any]],
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            )
            for msg in new_messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                metadata = msg.get("metadata")
                metadata_json = json.dumps(metadata) if metadata else None
                await db.execute(
                    """INSERT INTO conversations (conversation_id, role, content, metadata)
                       VALUES (?, ?, ?, ?)""",
                    (conversation_id, role, content, metadata_json),
                )
            await db.commit()

        try:
            try:
                self.collection.delete(where={"conversation_id": conversation_id})
            except Exception:
                pass

            msg_id = 0
            for msg in new_messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                meta = msg.get("metadata", {})
                if content and len(content) > _MIN_INDEX_CHARS and role in _INDEXABLE_ROLES:
                    try:
                        m = {
                            "conversation_id": conversation_id,
                            "role": role,
                            "timestamp": datetime.now().isoformat(),
                            "message_id": str(msg_id),
                        }
                        if isinstance(meta, dict):
                            m["type"] = meta.get("type", "")
                            if meta.get("tool_name"):
                                m["tool_name"] = str(meta["tool_name"])
                        self.collection.add(
                            documents=[content],
                            metadatas=[m],
                            ids=[f"{conversation_id}_{msg_id}"],
                        )
                    except Exception:
                        pass
                msg_id += 1
        except Exception:
            pass

        return len(new_messages)

    async def delete_conversation(self, conversation_id: str) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "DELETE FROM conversations WHERE conversation_id = ?",
                    (conversation_id,),
                )
                await db.commit()
            try:
                self.collection.delete(where={"conversation_id": conversation_id})
            except Exception:
                pass
            return True
        except Exception:
            return False

    async def list_recent_conversations(self, limit: int = 10) -> list[dict]:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    """
                    SELECT
                        conversation_id,
                        MAX(timestamp) as last_timestamp,
                        COUNT(*) as message_count,
                        (SELECT role FROM conversations c2
                         WHERE c2.conversation_id = c.conversation_id
                         ORDER BY timestamp DESC LIMIT 1) as last_role
                    FROM conversations c
                    GROUP BY conversation_id
                    ORDER BY last_timestamp DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = await cursor.fetchall()
                return [
                    {
                        "conversation_id": row["conversation_id"],
                        "last_timestamp": row["last_timestamp"],
                        "message_count": row["message_count"],
                        "last_role": row["last_role"] or "unknown",
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.warning("Error listing conversations: %s", e)
            return []