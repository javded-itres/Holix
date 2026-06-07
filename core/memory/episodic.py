"""
Episodic Memory Store for Helix Long-term Memory.

Stores compact narrative summaries of past conversations and tasks.
Each episode captures: what happened, what the outcome was, and what was learned.
Automatically generated when conversations end or are compressed.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiosqlite
from openai import AsyncOpenAI

from core.memory.vector import VectorMemoryStore

logger = logging.getLogger(__name__)


class EpisodicMemoryStore:
    """Manages episodic memory — memories of past experiences and conversations.

    Episodes are compact narrative summaries, not raw conversation logs.
    They capture the essence of what happened and what was learned,
    making them efficient for retrieval and context injection.
    """

    def __init__(self, db_path: str, vector_store: VectorMemoryStore):
        self._db_path = db_path
        self._vector_store = vector_store

    async def store_episode(
        self,
        conversation_id: str,
        summary: str,
        outcome: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Store an episodic memory entry.

        Args:
            conversation_id: Source conversation ID.
            summary: Compact narrative summary of the experience.
            outcome: "success" | "failure" | "partial" — what was the result.
            metadata: Optional additional metadata.

        Returns:
            Row ID in ltm_entries table.
        """
        meta = metadata or {}
        meta["conversation_id"] = conversation_id
        meta["outcome"] = outcome
        meta["timestamp"] = datetime.now().isoformat()

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """INSERT INTO ltm_entries (memory_type, content, source, category, metadata)
                   VALUES ('episodic', ?, ?, 'conversation', ?)""",
                (summary, conversation_id, json.dumps(meta)),
            )
            entry_id = cursor.lastrowid
            await db.commit()

        # Index in vector store for semantic search
        self._vector_store.upsert(
            collection_name="ltm_episodic",
            documents=[summary],
            ids=[f"episodic_{entry_id}"],
            metadatas=[meta],
        )

        return entry_id

    async def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Semantic search across episodic memories.

        Args:
            query: Search query.
            top_k: Number of results.

        Returns:
            List of matching episodes with content, metadata, distance.
        """
        results = self._vector_store.query(
            "ltm_episodic", [query], n_results=top_k
        )

        episodes = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results.get("distances") else None
                episodes.append({
                    "content": doc,
                    "metadata": meta,
                    "distance": distance,
                    "conversation_id": meta.get("conversation_id", ""),
                    "outcome": meta.get("outcome", "unknown"),
                })

        return episodes

    async def get_episodes_for_conversation(
        self,
        conversation_id: str,
    ) -> List[Dict[str, Any]]:
        """Get all episodic entries for a specific conversation.

        Args:
            conversation_id: Conversation identifier.

        Returns:
            List of episode dicts.
        """
        episodes = []
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT id, content, metadata, created_at
                   FROM ltm_entries
                   WHERE memory_type = 'episodic' AND source = ?
                   ORDER BY created_at DESC""",
                (conversation_id,),
            )
            rows = await cursor.fetchall()
            for row in rows:
                meta = {}
                if row["metadata"]:
                    try:
                        meta = json.loads(row["metadata"])
                    except json.JSONDecodeError:
                        pass
                episodes.append({
                    "id": row["id"],
                    "content": row["content"],
                    "metadata": meta,
                    "created_at": row["created_at"],
                })

        return episodes

    async def auto_summarize_conversation(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
        llm_client: AsyncOpenAI,
        model: str = "",
    ) -> Optional[str]:
        """Automatically generate and store an episodic summary of a conversation.

        Uses the LLM to create a compact narrative from the conversation messages.

        Args:
            conversation_id: Conversation identifier.
            messages: List of conversation messages.
            llm_client: OpenAI client for summarization.
            model: Model name for the LLM call.

        Returns:
            Generated summary string, or None if summarization failed.
        """
        if not messages or len(messages) < 2:
            return None

        # Build conversation excerpt for the LLM
        excerpt_parts = []
        for msg in messages[-30:]:  # Use last 30 messages max
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if not content:
                continue
            # Truncate long messages
            truncated = content[:300] + "..." if len(content) > 300 else content
            excerpt_parts.append(f"{role.upper()}: {truncated}")

        excerpt = "\n".join(excerpt_parts)
        if len(excerpt) > 3000:
            excerpt = excerpt[:3000] + "..."

        prompt = f"""Summarize this conversation as a compact episodic memory entry.
Focus on: what was requested, what actions were taken, what was the outcome.

Conversation:
{excerpt}

Provide your response in this format:
SUMMARY: (1-3 sentence narrative summary)
OUTCOME: (success/failure/partial)
KEY_LEARNING: (one key takeaway, if any)"""

        try:
            effective_model = (model or "").strip()
            if not effective_model:
                logger.warning("Episodic summary skipped: no model provided")
                return None

            response = await llm_client.chat.completions.create(
                model=effective_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at creating compact episodic memory summaries from conversations. Be concise and factual.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=300,
            )

            result_text = response.choices[0].message.content or ""

            # Parse the structured response
            summary = ""
            outcome = "partial"
            key_learning = ""

            for line in result_text.strip().split("\n"):
                if line.startswith("SUMMARY:"):
                    summary = line.replace("SUMMARY:", "").strip()
                elif line.startswith("OUTCOME:"):
                    outcome = line.replace("OUTCOME:", "").strip().lower()
                    if outcome not in ("success", "failure", "partial"):
                        outcome = "partial"
                elif line.startswith("KEY_LEARNING:"):
                    key_learning = line.replace("KEY_LEARNING:", "").strip()

            if not summary:
                # Fallback: use the entire response as summary
                summary = result_text[:200]

            # Store the episode
            metadata = {}
            if key_learning:
                metadata["key_learning"] = key_learning

            await self.store_episode(
                conversation_id=conversation_id,
                summary=summary,
                outcome=outcome,
                metadata=metadata,
            )

            return summary

        except Exception as e:
            logger.warning(f"Auto-summarization failed for {conversation_id}: {e}")
            # Fallback: simple statistical summary
            user_msgs = [m for m in messages if m.get("role") == "user"]
            tool_msgs = [m for m in messages if m.get("role") == "tool"]
            simple_summary = (
                f"Conversation with {len(user_msgs)} user messages and "
                f"{len(tool_msgs)} tool calls."
            )
            try:
                await self.store_episode(
                    conversation_id=conversation_id,
                    summary=simple_summary,
                    outcome="partial",
                    metadata={"auto_generated": True, "fallback": True},
                )
            except Exception:
                pass

            return simple_summary