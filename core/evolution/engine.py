"""
Evolution Engine — closes the self-evolution loop.

After every task completion, the Evolution Engine:
1. Saves an episodic memory entry (what was done, mode, sub-agents, success)
2. Updates strategic memory (which mode works best for which task types)
3. Records sub-agent outcomes in procedural memory
4. If self-refinement occurred, saves before/after patterns

This creates a feedback loop:
  Task -> Execution -> Assessment -> Memory -> Future Decisions
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class EvolutionEngine:
    """Closes the self-evolution loop by recording experiences
    and updating strategic memory.

    Called after each task completion via finalize_node.
    """

    def __init__(self, memory: Any | None = None):
        """Initialize the evolution engine.

        Args:
            memory: LongTermMemoryManager instance.
        """
        self._memory = memory

    def set_memory(self, memory: Any) -> None:
        """Set the memory manager (called after initialization)."""
        self._memory = memory

    async def after_task_completed(
        self,
        task: str,
        result: str,
        sub_agents_used: list[str] | None = None,
        mode: str = "react",
        duration_ms: float = 0.0,
        success: bool = True,
        conversation_id: str = "default",
    ) -> None:
        """Record the outcome of a completed task.

        Called after finalize_node finishes. Saves experience to
        episodic, strategic, and procedural memory.

        Args:
            task: The user's original task/query.
            result: The agent's final response.
            sub_agents_used: List of sub-agent names used (if any).
            mode: Execution mode used (react, plan_and_execute, hybrid).
            duration_ms: How long the task took in milliseconds.
            success: Whether the task completed successfully.
            conversation_id: Conversation identifier.
        """
        if not self._memory or not hasattr(self._memory, "episodic"):
            logger.debug("EvolutionEngine: no memory available, skipping")
            return

        sub_agents_used = sub_agents_used or []

        # 1. Save episodic memory
        await self._save_episodic(
            task=task,
            result=result,
            sub_agents_used=sub_agents_used,
            mode=mode,
            duration_ms=duration_ms,
            success=success,
            conversation_id=conversation_id,
        )

        # 2. Update strategic memory (mode preferences)
        await self._update_strategic_memory(
            task=task,
            mode=mode,
            success=success,
            duration_ms=duration_ms,
        )

        # 3. Record sub-agent outcomes
        if sub_agents_used:
            await self._record_sub_agent_outcomes(
                sub_agents_used=sub_agents_used,
                success=success,
                task=task,
            )

        logger.info(
            f"Evolution: recorded task outcome "
            f"(mode={mode}, success={success}, "
            f"duration={duration_ms:.0f}ms, "
            f"sub_agents={len(sub_agents_used)})"
        )

    async def _save_episodic(
        self,
        task: str,
        result: str,
        sub_agents_used: list[str],
        mode: str,
        duration_ms: float,
        success: bool,
        conversation_id: str,
    ) -> None:
        """Save an episodic memory of the task."""
        outcome = "success" if success else "failure"
        sub_agents_str = ", ".join(sub_agents_used) if sub_agents_used else "none"

        summary = (
            f"Task: {task[:200]}. "
            f"Mode: {mode}. "
            f"Sub-agents: {sub_agents_str}. "
            f"Duration: {duration_ms:.0f}ms. "
            f"Outcome: {outcome}."
        )

        try:
            await self._memory.episodic.store_episode(
                conversation_id=conversation_id,
                summary=summary,
                outcome=outcome,
                metadata={
                    "type": "evolution",
                    "mode": mode,
                    "sub_agents": sub_agents_used,
                    "duration_ms": duration_ms,
                    "success": success,
                    "task_length": len(task),
                },
            )
        except Exception as e:
            logger.warning(f"Evolution: failed to save episodic: {e}")

    async def _update_strategic_memory(
        self,
        task: str,
        mode: str,
        success: bool,
        duration_ms: float,
    ) -> None:
        """Update strategic memory with mode preferences."""
        task_type = self._classify_task(task)
        key = f"mode_preference_{task_type}"

        try:
            existing = await self._memory.strategic.get_fact(key)

            if existing:
                content = existing.get("content", "")
                new_content = self._update_mode_stats(
                    existing_content=content,
                    mode=mode,
                    success=success,
                    duration_ms=duration_ms,
                )
                await self._memory.strategic.store_strategy(
                    key=key,
                    content=new_content,
                    category="execution_mode",
                    source="evolution",
                )
            else:
                content = f"mode {mode}: {100 if success else 0}% success in {duration_ms:.0f}ms avg (1 task)"
                await self._memory.strategic.store_strategy(
                    key=key,
                    content=content,
                    category="execution_mode",
                    source="evolution",
                    metadata={
                        "task_type": task_type,
                        "mode": mode,
                        "success": success,
                        "duration_ms": duration_ms,
                    },
                )

        except Exception as e:
            logger.warning(f"Evolution: failed to update strategic memory: {e}")

    async def _record_sub_agent_outcomes(
        self,
        sub_agents_used: list[str],
        success: bool,
        task: str,
    ) -> None:
        """Record sub-agent usage outcomes in procedural memory."""
        for agent_name in sub_agents_used:
            try:
                await self._memory.procedural.record_skill_outcome(
                    skill_name=f"sub_agent_{agent_name}",
                    task_description=task[:200],
                    success=success,
                    context={
                        "sub_agent": agent_name,
                        "task_type": self._classify_task(task),
                    },
                )
            except Exception as e:
                logger.warning(f"Evolution: failed to record sub-agent outcome: {e}")

    def _classify_task(self, task: str) -> str:
        """Classify a task into a type category."""
        task_lower = task.lower()

        if any(kw in task_lower for kw in ["code", "implement", "function", "class", "debug", "fix", "refactor"]):
            return "coding"
        elif any(kw in task_lower for kw in ["research", "find", "search", "analyze", "investigate", "explain"]):
            return "research"
        elif any(kw in task_lower for kw in ["write", "document", "readme", "comment", "blog", "article"]):
            return "writing"
        elif any(kw in task_lower for kw in ["data", "sql", "query", "database", "chart", "visual"]):
            return "data_analysis"
        elif any(kw in task_lower for kw in ["test", "verify", "check", "review", "audit"]):
            return "testing"
        elif any(kw in task_lower for kw in ["deploy", "setup", "configure", "install", "docker"]):
            return "devops"
        else:
            return "general"

    def _update_mode_stats(
        self,
        existing_content: str,
        mode: str,
        success: bool,
        duration_ms: float,
    ) -> str:
        """Update mode statistics in existing strategy content."""
        try:
            pattern = rf"mode {mode}:\s*(\d+)% success in (\d+)ms avg \((\d+) tasks\)"
            match = re.search(pattern, existing_content)

            if match:
                old_success_rate = int(match.group(1))
                old_duration = int(match.group(2))
                old_count = int(match.group(3))

                new_success = 1 if success else 0
                new_count = old_count + 1
                new_success_rate = int((old_success_rate * old_count + new_success * 100) / new_count)
                new_duration = int((old_duration * old_count + duration_ms) / new_count)

                new_entry = f"mode {mode}: {new_success_rate}% success in {new_duration}ms avg ({new_count} tasks)"
                return existing_content[:match.start()] + new_entry + existing_content[match.end():]

        except Exception:
            pass

        return f"{existing_content}; mode {mode}: {100 if success else 0}% success in {duration_ms:.0f}ms (1 task)"