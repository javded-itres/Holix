"""Long-term typed memory stores (episodic, semantic, procedural, strategic)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

from core.di.runtime_config import HelixRuntimeConfig
from core.memory.episodic import EpisodicMemoryStore
from core.memory.procedural import ProceduralMemoryStore
from core.memory.semantic import SemanticMemoryStore
from core.memory.strategic import StrategicMemoryStore
from core.memory.vector import VectorMemoryStore

logger = logging.getLogger(__name__)


class LongTermMemoryStore:
    """Typed long-term memory backed by SQLite + shared ChromaDB collections."""

    def __init__(self, config: HelixRuntimeConfig | None = None):
        cfg = config or HelixRuntimeConfig.from_settings()
        self.config = cfg
        self._ltm_db_path = Path(cfg.ltm_db_path)
        self._ltm_db_path.parent.mkdir(parents=True, exist_ok=True)

        self._vector_store = VectorMemoryStore(vector_db_path=cfg.vector_db_path)

        self.episodic = EpisodicMemoryStore(
            db_path=str(self._ltm_db_path),
            vector_store=self._vector_store,
        )
        self.semantic = SemanticMemoryStore(
            db_path=str(self._ltm_db_path),
            vector_store=self._vector_store,
        )
        self.procedural = ProceduralMemoryStore(
            db_path=str(self._ltm_db_path),
            vector_store=self._vector_store,
        )
        self.strategic = StrategicMemoryStore(
            db_path=str(self._ltm_db_path),
            vector_store=self._vector_store,
        )

    async def initialize_db(self) -> None:
        async with aiosqlite.connect(self._ltm_db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ltm_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_type TEXT NOT NULL CHECK(memory_type IN ('episodic', 'semantic', 'procedural', 'strategic')),
                    key TEXT,
                    content TEXT NOT NULL,
                    source TEXT,
                    category TEXT,
                    metadata TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(key, memory_type)
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_ltm_type ON ltm_entries(memory_type)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_ltm_source ON ltm_entries(source)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_ltm_category ON ltm_entries(category)
            """)
            await db.commit()

    async def store_fact(
        self,
        key: str,
        content: str,
        source: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        return await self.semantic.store_fact(key, content, source, metadata)

    async def get_fact(self, key: str) -> Optional[Dict[str, Any]]:
        return await self.semantic.get_fact(key)

    async def search_episodes(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return await self.episodic.search(query, top_k)

    async def store_strategy(
        self,
        key: str,
        content: str,
        category: str = "general",
        source: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        return await self.strategic.store_strategy(
            key, content, category, source, metadata
        )

    async def search_strategies(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return await self.strategic.search(query, top_k)

    async def get_relevant_context(
        self,
        query: str,
        top_k: int = 5,
    ) -> Dict[str, List[Dict[str, Any]]]:
        import asyncio

        episodic, semantic, strategic = await asyncio.gather(
            self.episodic.search(query, top_k),
            self.semantic.search(query, top_k),
            self.strategic.search(query, top_k),
        )
        return {
            "episodic": episodic,
            "semantic": semantic,
            "strategic": strategic,
        }

    def set_skills_manager(self, skills_manager: Any) -> None:
        self.procedural.set_skills_manager(skills_manager)

    def get_memory_stats(self) -> Dict[str, Any]:
        return {"vector_store": self._vector_store.get_stats()}