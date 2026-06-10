"""
Meta-Agent — lightweight advisory agent that monitors and adjusts agent behavior.

The Meta-Agent is NOT a separate full agent. It is a strategic advisory
layer that runs at two specific points in the graph:

1. Pre-thinking (after memory retrieval): Reviews context and user input,
   decides if the current execution mode is appropriate, and optionally
   injects strategic memory or adjusts the approach.

2. Post-completion (after finalize): Evaluates whether the response
   meets quality criteria. If not, suggests a refinement iteration.

Uses the same AsyncOpenAI client with low temperature and compact prompts
(~200 tokens) to minimize latency overhead.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class MetaDecision:
    """Decision from the meta-agent's pre-thinking analysis.

    This is injected into the graph state and used by subsequent nodes
    to adjust behavior.
    """

    # Should the execution mode be changed?
    suggested_mode: str = ""  # "react" | "plan_and_execute" | "hybrid" | "" (no change)

    # Should strategic memories be injected?
    inject_strategies: list[dict[str, Any]] = field(default_factory=list)

    # Additional context to add to the system prompt
    context_hint: str = ""

    # Confidence in this decision (0.0 - 1.0)
    confidence: float = 0.5

    # Reasoning behind the decision (for debugging/logging)
    reasoning: str = ""


@dataclass
class QualityAssessment:
    """Assessment of a completed response from the meta-agent.

    Used to determine if self-refinement is needed.
    """

    # Overall quality score (0.0 - 1.0)
    quality_score: float = 0.5

    # Does the response need refinement?
    needs_refinement: bool = False

    # What specifically could be improved?
    improvement_areas: list[str] = field(default_factory=list)

    # Suggested refinement prompt (for self-refinement loop)
    refinement_prompt: str = ""

    # Reasoning (for debugging/logging)
    reasoning: str = ""


# System prompts — kept short (~200 tokens each)

META_ANALYZE_PROMPT = """You are a meta-cognitive advisor for an AI agent. Analyze the task and suggest the best approach.

Based on the user's input and available context:
1. Should the execution mode change? (react for simple tasks, plan_and_execute for multi-step, hybrid for complex)
2. Are there strategic insights to inject?
3. Any special considerations?

Respond in JSON:
{{"suggested_mode": "react|plan_and_execute|hybrid|", "context_hint": "brief hint", "confidence": 0.0-1.0, "reasoning": "why"}}"""

META_EVALUATE_PROMPT = """You are a quality assessor for an AI agent. Evaluate the response quality.

Rate the response on:
- Completeness: Does it fully address the user's question?
- Accuracy: Is the information correct?
- Clarity: Is it well-structured and easy to understand?
- Actionability: Does it provide concrete, useful guidance?

Respond in JSON:
{{"quality_score": 0.0-1.0, "needs_refinement": true/false, "improvement_areas": ["area1", ...], "refinement_prompt": "what to improve", "reasoning": "why"}}"""


class MetaAgent:
    """Lightweight meta-cognitive advisory agent.

    Provides strategic guidance without tool usage — only reasons
    about the task and response quality.
    """

    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        model: str = "",
    ):
        """Initialize the meta-agent.

        Args:
            client: OpenAI client (set later if not provided).
            model: Model for meta-agent calls (empty = use default).
        """
        self._client = client
        self._model = model or settings.model

    def set_client(self, client: AsyncOpenAI) -> None:
        """Set the OpenAI client."""
        self._client = client

    async def analyze_task(
        self,
        user_input: str,
        context: dict[str, Any] | None = None,
        memories: dict[str, Any] | None = None,
    ) -> MetaDecision:
        """Analyze a task before execution and suggest adjustments.

        Runs a lightweight LLM call to:
        - Determine if the execution mode should change
        - Suggest strategic memory injection
        - Provide context hints

        Args:
            user_input: The user's task/query.
            context: Current graph state context.
            memories: Relevant memories from LTM.

        Returns:
            MetaDecision with suggestions.
        """
        if not self._client:
            logger.debug("Meta-agent: no client, returning default decision")
            return MetaDecision()

        # Build context section
        context_str = self._build_context_str(context, memories)

        prompt = f"""Task: {user_input[:500]}

Context: {context_str}

{META_ANALYZE_PROMPT}"""

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You are a strategic advisor. Respond only with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=200,
            )

            result_text = response.choices[0].message.content or ""
            return self._parse_meta_decision(result_text)

        except Exception as e:
            logger.warning(f"Meta-agent analysis failed: {e}")
            return MetaDecision(reasoning=f"Analysis failed: {e}")

    async def evaluate_response(
        self,
        response: str,
        original_task: str,
        context: dict[str, Any] | None = None,
    ) -> QualityAssessment:
        """Evaluate a completed response for quality.

        Runs a lightweight LLM call to assess:
        - Completeness, accuracy, clarity, actionability
        - Whether refinement is needed
        - What specifically to improve

        Args:
            response: The agent's final response.
            original_task: The user's original task/query.
            context: Optional context from the execution.

        Returns:
            QualityAssessment with scores and improvement suggestions.
        """
        if not self._client:
            logger.debug("Meta-agent: no client, returning default assessment")
            return QualityAssessment()

        prompt = f"""Original task: {original_task[:300]}

Agent response: {response[:1000]}

{META_EVALUATE_PROMPT}"""

        try:
            response_obj = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You are a quality assessor. Respond only with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=200,
            )

            result_text = response_obj.choices[0].message.content or ""
            return self._parse_quality_assessment(result_text)

        except Exception as e:
            logger.warning(f"Meta-agent evaluation failed: {e}")
            return QualityAssessment(reasoning=f"Evaluation failed: {e}")

    def _build_context_str(
        self,
        context: dict[str, Any] | None,
        memories: dict[str, Any] | None,
    ) -> str:
        """Build a compact context string for the meta-agent prompt."""
        parts = []

        if context:
            mode = context.get("execution_mode", "react")
            step = context.get("step_count", 0)
            parts.append(f"Mode: {mode}, Step: {step}")

        if memories:
            # Include only key points from memories
            for mem_type in ["episodic", "semantic", "strategic"]:
                mems = memories.get(mem_type, [])
                if mems:
                    for m in mems[:2]:  # Top 2 per type
                        content = m.get("content", "")[:100]
                        parts.append(f"[{mem_type}]: {content}")

        return "; ".join(parts) if parts else "No additional context"

    def _parse_meta_decision(self, text: str) -> MetaDecision:
        """Parse the meta-agent's analysis response."""
        import json

        try:
            # Try to extract JSON
            text = text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1])

            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                data = json.loads(text[start:end + 1])
                return MetaDecision(
                    suggested_mode=data.get("suggested_mode", ""),
                    context_hint=data.get("context_hint", ""),
                    confidence=float(data.get("confidence", 0.5)),
                    reasoning=data.get("reasoning", ""),
                )
        except (json.JSONDecodeError, ValueError):
            pass

        return MetaDecision(reasoning="Could not parse meta-agent response")

    def _parse_quality_assessment(self, text: str) -> QualityAssessment:
        """Parse the meta-agent's quality assessment response."""
        import json

        try:
            text = text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1])

            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                data = json.loads(text[start:end + 1])
                return QualityAssessment(
                    quality_score=float(data.get("quality_score", 0.5)),
                    needs_refinement=bool(data.get("needs_refinement", False)),
                    improvement_areas=data.get("improvement_areas", []),
                    refinement_prompt=data.get("refinement_prompt", ""),
                    reasoning=data.get("reasoning", ""),
                )
        except (json.JSONDecodeError, ValueError):
            pass

        return QualityAssessment(reasoning="Could not parse quality assessment")