import json
import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings

from config import settings


class MemoryManager:
    """Manages conversation memory with SQLite and vector search."""

    def __init__(self):
        self.db_path = Path(settings.memory_db_path)
        self.vector_db_path = Path(settings.vector_db_path)

        # Ensure directories exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.vector_db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB
        self.chroma_client = chromadb.PersistentClient(
            path=str(self.vector_db_path),
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name="memory",
            metadata={"hnsw:space": "cosine"}
        )

    async def initialize_db(self):
        """Initialize SQLite database schema."""
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
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Save a message to both SQLite and vector DB.

        Args:
            conversation_id: Conversation identifier
            role: Message role (user/assistant/system/tool)
            content: Message content
            metadata: Optional metadata

        Returns:
            Message ID
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO conversations (conversation_id, role, content, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, role, content, json.dumps(metadata or {}))
            )
            message_id = cursor.lastrowid
            await db.commit()

        # Add to vector DB if it's a substantial message
        if content and len(content) > 10 and role in ["user", "assistant"]:
            try:
                self.collection.add(
                    documents=[content],
                    metadatas=[{
                        "conversation_id": conversation_id,
                        "role": role,
                        "timestamp": datetime.now().isoformat(),
                        "message_id": str(message_id)
                    }],
                    ids=[f"{conversation_id}_{message_id}"]
                )
            except Exception as e:
                print(f"Warning: Failed to add to vector DB: {e}")

        return message_id

    async def get_conversation(
        self,
        conversation_id: str,
        limit: int = 30
    ) -> List[Dict[str, Any]]:
        """Get recent messages from a conversation.

        Args:
            conversation_id: Conversation identifier
            limit: Maximum number of messages to retrieve

        Returns:
            List of messages
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT role, content, timestamp, metadata
                FROM conversations
                WHERE conversation_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (conversation_id, limit)
            )

            rows = await cursor.fetchall()

            # Reverse to get chronological order
            messages = []
            for row in reversed(rows):
                msg = {
                    "role": row["role"],
                    "content": row["content"]
                }
                if row["metadata"]:
                    try:
                        metadata = json.loads(row["metadata"])
                        if metadata:
                            msg["metadata"] = metadata
                    except json.JSONDecodeError:
                        pass
                messages.append(msg)

            return messages

    async def search(
        self,
        query: str,
        top_k: int = 8,
        conversation_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Semantic search across memory.

        Args:
            query: Search query
            top_k: Number of results to return
            conversation_id: Optional filter by conversation

        Returns:
            List of relevant memories
        """
        try:
            where_filter = None
            if conversation_id:
                where_filter = {"conversation_id": conversation_id}

            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter
            )

            memories = []
            if results["documents"] and results["documents"][0]:
                for i, doc in enumerate(results["documents"][0]):
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                    memories.append({
                        "content": doc,
                        "metadata": metadata,
                        "distance": results["distances"][0][i] if results.get("distances") else None
                    })

            return memories

        except Exception as e:
            print(f"Error during semantic search: {e}")
            return []

    async def summarize_conversation(
        self,
        conversation_id: str,
        llm_client=None
    ) -> str:
        """Generate a summary of the conversation.

        Args:
            conversation_id: Conversation identifier
            llm_client: Optional OpenAI client for summarization

        Returns:
            Conversation summary
        """
        messages = await self.get_conversation(conversation_id, limit=100)

        if not messages:
            return "No conversation history."

        # Simple summary without LLM
        user_msgs = [m for m in messages if m["role"] == "user"]
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]

        summary = f"Conversation summary:\n"
        summary += f"- Total messages: {len(messages)}\n"
        summary += f"- User messages: {len(user_msgs)}\n"
        summary += f"- Assistant messages: {len(assistant_msgs)}\n"

        # If LLM client provided, generate detailed summary
        if llm_client:
            # TODO: Implement LLM-based summarization
            pass

        return summary
