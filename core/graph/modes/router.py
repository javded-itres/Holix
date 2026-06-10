"""
ModeRouter — automatically selects the best execution mode for a task.

Uses a lightweight LLM call to classify the user's input into one of:
- "react": Interactive, exploratory, tool-heavy tasks (default)
- "plan_and_execute": Multi-step tasks with clear subgoals
- "hybrid": Complex tasks requiring planning + per-step ReAct

Falls back to "react" on any failure (LLM timeout, parse error, etc.).
"""

import logging
from typing import Any

from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)

# Prompt for mode classification — kept minimal (~200 tokens)
MODE_CLASSIFICATION_PROMPT = """Classify the following task into exactly one execution mode.

Modes:
- react: Interactive, exploratory tasks. Best for: single-step queries, tool usage, quick lookups, coding help.
- plan_and_execute: Multi-step tasks with clear subgoals. Best for: "refactor X and add tests", "migrate from A to B", "set up a project with these features".
- hybrid: Complex tasks requiring both planning and flexible execution. Best for: "design and implement a full system", "research and then build".

Task: {task}

Respond with ONLY the mode name (react, plan_and_execute, or hybrid). No explanation."""


class ModeRouter:
    """Selects the best execution mode for a given task.

    Uses a lightweight LLM call for classification. Falls back to
    the default mode on any failure (timeout, parse error, etc.).
    """

    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        model: str = "",
        default_mode: str = "react",
    ):
        """Initialize the mode router.

        Args:
            client: OpenAI client (if None, will need to be set later).
            model: Model for classification calls (empty = use default).
            default_mode: Fallback mode when classification fails.
        """
        self._client = client
        self._model = model or settings.model
        self._default_mode = default_mode
        # Track routing history for learning
        self._routing_history: list[dict[str, Any]] = []

    def set_client(self, client: AsyncOpenAI) -> None:
        """Set the OpenAI client (called after agent initialization)."""
        self._client = client

    async def select_mode(
        self,
        user_input: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Select the best execution mode for a task.

        Args:
            user_input: The user's task/query.
            context: Optional context (conversation history, skills, etc.).

        Returns:
            One of "react", "plan_and_execute", or "hybrid".
        """
        if not self._client:
            logger.debug("No LLM client for mode routing, falling back to default")
            return self._default_mode

        # Truncate long inputs to keep the classification prompt short
        task = user_input[:500] if len(user_input) > 500 else user_input

        prompt = MODE_CLASSIFICATION_PROMPT.format(task=task)

        # Add context hint if available
        if context and context.get("relevant_strategies"):
            # Check if strategic memory suggests a mode preference
            strategies = context["relevant_strategies"]
            for s in strategies:
                key = s.get("key", "")
                if "execution_mode" in key or "mode" in key.lower():
                    content = s.get("content", "").lower()
                    if "plan_and_execute" in content:
                        logger.info("Strategic memory suggests plan_and_execute mode")
                        return "plan_and_execute"
                    elif "hybrid" in content:
                        logger.info("Strategic memory suggests hybrid mode")
                        return "hybrid"

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": "You classify tasks into execution modes. Respond with ONLY the mode name.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,  # Deterministic classification
                max_tokens=10,    # Very short response
            )

            mode_text = response.choices[0].message.content or ""
            mode = mode_text.strip().lower()

            # Validate the mode
            valid_modes = {"react", "plan_and_execute", "hybrid"}
            if mode in valid_modes:
                logger.info(f"Mode router selected: {mode} for task: {task[:80]}...")

                # Record routing decision for learning
                self._routing_history.append({
                    "task": task[:200],
                    "selected_mode": mode,
                    "context_keys": list(context.keys()) if context else [],
                })

                return mode

            # If LLM returned something unexpected, fall back
            logger.warning(f"Mode router returned invalid mode '{mode}', falling back to {self._default_mode}")
            return self._default_mode

        except Exception as e:
            logger.warning(f"Mode router failed: {e}, falling back to {self._default_mode}")
            return self._default_mode

    def get_routing_stats(self) -> dict[str, Any]:
        """Get statistics about mode routing decisions.

        Returns:
            Dict with mode counts and recent routing history.
        """
        mode_counts: dict[str, int] = {}
        for entry in self._routing_history:
            mode = entry.get("selected_mode", "unknown")
            mode_counts[mode] = mode_counts.get(mode, 0) + 1

        return {
            "total_routing_decisions": len(self._routing_history),
            "mode_distribution": mode_counts,
            "recent_decisions": self._routing_history[-10:],
        }