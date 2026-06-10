"""
Procedural Memory Store for Helix Long-term Memory.

Backed by the existing SkillsManager for skill definitions,
plus outcome tracking in ltm_entries. Enriches skill retrieval
with historical success/failure data to improve recommendations.
"""

import json
import logging
from datetime import datetime
from typing import Any

import aiosqlite

from core.memory.vector import VectorMemoryStore

logger = logging.getLogger(__name__)


class ProceduralMemoryStore:
    """Manages procedural memory — skills and their usage outcomes.

    Does NOT duplicate skill definitions (those live in SkillsManager).
    Instead, tracks HOW skills have been used: which tasks they were
    applied to, whether they succeeded, and contextual notes.

    This enrichment allows ranking skills by both relevance AND
    historical success rate.
    """

    def __init__(
        self,
        db_path: str,
        vector_store: VectorMemoryStore,
        skills_manager: Any | None = None,
    ):
        self._db_path = db_path
        self._vector_store = vector_store
        self._skills_manager = skills_manager  # Injected later to avoid circular imports

    def set_skills_manager(self, skills_manager: Any) -> None:
        """Set the SkillsManager instance (called after initialization).

        Args:
            skills_manager: The SkillsManager instance.
        """
        self._skills_manager = skills_manager

    async def search(
        self,
        query: str,
        top_k: int = 5,
        *,
        agent_slot: str = "main",
    ) -> list[dict[str, Any]]:
        """Search for relevant skills, enriched with outcome data.

        Delegates to SkillsManager.get_relevant_skills() for relevance,
        then enriches each result with success/failure stats from ltm_entries.

        Args:
            query: Search query.
            top_k: Number of results.

        Returns:
            List of skill dicts enriched with outcome stats.
        """
        if not self._skills_manager:
            return []

        # Get relevant skills from SkillsManager
        skills = self._skills_manager.get_relevant_skills(
            query, top_k=top_k, agent_slot=agent_slot
        )

        if not skills:
            return []

        # Enrich with outcome data from ltm_entries
        enriched = []
        for skill in skills:
            skill_name = skill.get("name", "")
            outcome_data = await self._get_skill_outcomes(skill_name)
            enriched.append({
                **skill,
                "outcome_stats": outcome_data,
            })

        return enriched

    async def record_skill_outcome(
        self,
        skill_name: str,
        task_description: str,
        success: bool,
        context: dict[str, Any] | None = None,
    ) -> int:
        """Record the outcome of using a skill for a task.

        This data is used to rank skills by both relevance AND success rate.

        Args:
            skill_name: Name of the skill used.
            task_description: Description of the task.
            success: Whether the skill usage was successful.
            context: Optional contextual information.

        Returns:
            Row ID in ltm_entries table.
        """
        meta = context or {}
        meta["skill_name"] = skill_name
        meta["success"] = success
        meta["timestamp"] = datetime.now().isoformat()

        outcome_str = "success" if success else "failure"
        content = f"Skill '{skill_name}' used for: {task_description[:200]} — outcome: {outcome_str}"

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """INSERT INTO ltm_entries (memory_type, content, source, category, metadata)
                   VALUES ('procedural', ?, ?, 'skill_outcome', ?)""",
                (content, skill_name, json.dumps(meta)),
            )
            entry_id = cursor.lastrowid
            await db.commit()

        return entry_id

    async def _get_skill_outcomes(
        self,
        skill_name: str,
    ) -> dict[str, Any]:
        """Get aggregated outcome statistics for a skill.

        Args:
            skill_name: Name of the skill.

        Returns:
            Dict with success_count, failure_count, success_rate, recent_outcomes.
        """
        stats = {
            "success_count": 0,
            "failure_count": 0,
            "success_rate": 0.0,
            "recent_outcomes": [],
        }

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT metadata, created_at
                   FROM ltm_entries
                   WHERE memory_type = 'procedural' AND source = ?
                   ORDER BY created_at DESC
                   LIMIT 20""",
                (skill_name,),
            )
            rows = await cursor.fetchall()

            for row in rows:
                try:
                    meta = json.loads(row["metadata"]) if row["metadata"] else {}
                    if meta.get("success"):
                        stats["success_count"] += 1
                    else:
                        stats["failure_count"] += 1

                    if len(stats["recent_outcomes"]) < 5:
                        stats["recent_outcomes"].append({
                            "success": meta.get("success", False),
                            "timestamp": row["created_at"],
                        })
                except (json.JSONDecodeError, KeyError):
                    continue

        total = stats["success_count"] + stats["failure_count"]
        if total > 0:
            stats["success_rate"] = stats["success_count"] / total

        return stats

    async def get_skill_recommendations(
        self,
        task_description: str,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Get skill recommendations ranked by relevance AND success rate.

        Args:
            task_description: Description of the current task.
            top_k: Number of recommendations.

        Returns:
            List of recommended skills with combined score.
        """
        skills = await self.search(task_description, top_k=top_k * 2)

        # Calculate combined score: relevance * success_rate
        # Relevance is derived from ChromaDB distance (lower = better)
        scored = []
        for skill in skills:
            distance = skill.get("relevance_distance", 1.0)
            relevance = max(0.0, 1.0 - distance)  # Convert distance to relevance (0-1)
            outcome_stats = skill.get("outcome_stats", {})
            success_rate = outcome_stats.get("success_rate", 0.5)  # Default to 0.5 if no data

            # Combined score: 70% relevance + 30% success rate
            # (relevance matters more, but success rate breaks ties)
            combined = 0.7 * relevance + 0.3 * success_rate
            skill["combined_score"] = combined
            scored.append(skill)

        # Sort by combined score descending
        scored.sort(key=lambda x: x.get("combined_score", 0), reverse=True)

        return scored[:top_k]