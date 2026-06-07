"""Unified memory facade for HelixAgent."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from core.di.runtime_config import HelixRuntimeConfig
from core.memory.conversation import ConversationStore
from core.memory.ltm import LongTermMemoryStore
from core.memory.summarizer import ConversationSummarizer


class MemoryFacade:
    """Single entry point for conversation + long-term memory.

    Composes ``ConversationStore`` and optional ``LongTermMemoryStore``.
    Exposes the legacy API used across the agent, graph nodes, and CLI.
    """

    def __init__(self, config: HelixRuntimeConfig | None = None):
        self.config = config or HelixRuntimeConfig.from_settings()
        self.conversations = ConversationStore(self.config)
        self._ltm: LongTermMemoryStore | None = None
        if self.config.enable_long_term_memory:
            self._ltm = LongTermMemoryStore(self.config)
        self._summarizer = ConversationSummarizer()

    @property
    def episodic(self):
        return self._require_ltm().episodic

    @property
    def semantic(self):
        return self._require_ltm().semantic

    @property
    def procedural(self):
        return self._require_ltm().procedural

    @property
    def strategic(self):
        return self._require_ltm().strategic

    def _require_ltm(self) -> LongTermMemoryStore:
        if self._ltm is None:
            raise RuntimeError("Long-term memory is disabled (enable_long_term_memory=False)")
        return self._ltm

    async def initialize_db(self) -> None:
        await self.conversations.initialize_db()
        if self._ltm:
            await self._ltm.initialize_db()

    # --- Conversation API (always available) ---

    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        return await self.conversations.save_message(
            conversation_id, role, content, metadata
        )

    async def get_conversation(
        self,
        conversation_id: str,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        return await self.conversations.get_conversation(conversation_id, limit)

    async def search(
        self,
        query: str,
        top_k: int = 8,
        conversation_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return await self.conversations.search(query, top_k, conversation_id)

    async def replace_conversation_messages(
        self,
        conversation_id: str,
        new_messages: List[Dict[str, Any]],
    ) -> int:
        return await self.conversations.replace_conversation_messages(
            conversation_id, new_messages
        )

    async def delete_conversation(self, conversation_id: str) -> bool:
        return await self.conversations.delete_conversation(conversation_id)

    async def list_recent_conversations(self, limit: int = 10) -> list[dict]:
        return await self.conversations.list_recent_conversations(limit)

    async def summarize_conversation(
        self,
        conversation_id: str,
        llm_client=None,
    ) -> str:
        return await self._summarizer.summarize_conversation(
            self.conversations, conversation_id, llm_client
        )

    # --- Long-term memory API ---

    async def store_fact(
        self,
        key: str,
        content: str,
        source: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        return await self._require_ltm().store_fact(key, content, source, metadata)

    async def get_fact(self, key: str) -> Optional[Dict[str, Any]]:
        return await self._require_ltm().get_fact(key)

    async def search_episodes(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return await self._require_ltm().search_episodes(query, top_k)

    async def store_strategy(
        self,
        key: str,
        content: str,
        category: str = "general",
        source: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        return await self._require_ltm().store_strategy(
            key, content, category, source, metadata
        )

    async def search_strategies(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return await self._require_ltm().search_strategies(query, top_k)

    async def get_relevant_context(
        self,
        query: str,
        top_k: int = 5,
    ) -> Dict[str, List[Dict[str, Any]]]:
        if not self._ltm:
            return {"episodic": [], "semantic": [], "strategic": []}
        return await self._ltm.get_relevant_context(query, top_k)

    async def auto_summarize_conversation(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
        llm_client: Optional[AsyncOpenAI] = None,
        model: str = "",
    ) -> Optional[str]:
        if not self._ltm:
            return None
        return await self._summarizer.auto_summarize(
            self._ltm,
            conversation_id,
            messages,
            llm_client=llm_client,
            model=model or self.config.model,
        )

    def set_skills_manager(self, skills_manager: Any) -> None:
        if self._ltm:
            self._ltm.set_skills_manager(skills_manager)

    def get_memory_stats(self) -> Dict[str, Any]:
        if not self._ltm:
            return {}
        return self._ltm.get_memory_stats()