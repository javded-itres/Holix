"""
Self-Refinement Loop — iteratively refines agent responses based on quality assessment.

Uses the MetaAgent's evaluate_response() to check quality after each
draft. If quality is below threshold, feeds back improvement suggestions
and re-runs the reasoning step. Each iteration appends a refinement
prompt to the messages.

Experiences are saved to long-term memory (episodic + strategic)
so the agent learns from its refinement history.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from core.meta_agent import MetaAgent, QualityAssessment

logger = logging.getLogger(__name__)


@dataclass
class RefinedOutput:
    """Result of the self-refinement process."""

    # The final (possibly refined) response
    response: str

    # Number of refinement iterations performed
    iterations: int = 0

    # Quality scores for each iteration
    quality_scores: list[float] = field(default_factory=list)

    # Whether the response was improved
    was_improved: bool = False

    # The final quality assessment
    final_assessment: QualityAssessment | None = None

    # Areas that were improved
    improvements: list[str] = field(default_factory=list)


class SelfRefinementLoop:
    """Iteratively refines agent responses using quality assessment.

    Each iteration:
    1. Evaluates the current response quality via MetaAgent
    2. If below threshold, generates a refinement prompt
    3. Appends the refinement prompt to messages
    4. Re-runs the reasoning step

    The loop terminates when:
    - Quality exceeds the threshold
    - Max iterations are reached
    - The response cannot be improved further
    """

    def __init__(
        self,
        meta_agent: MetaAgent | None = None,
        max_iterations: int = 2,
        quality_threshold: float = 0.7,
    ):
        """Initialize the self-refinement loop.

        Args:
            meta_agent: MetaAgent instance for quality assessment.
            max_iterations: Maximum refinement iterations.
            quality_threshold: Minimum quality score (0.0-1.0) to accept.
        """
        self._meta_agent = meta_agent
        self._max_iterations = max_iterations
        self._quality_threshold = quality_threshold

    def set_meta_agent(self, meta_agent: MetaAgent) -> None:
        """Set the MetaAgent instance."""
        self._meta_agent = meta_agent

    async def refine(
        self,
        state: dict[str, Any],
        max_iterations: int | None = None,
    ) -> RefinedOutput:
        """Run the self-refinement loop on a draft response.

        Args:
            state: Graph state dict containing messages, final_response, etc.
            max_iterations: Override max iterations for this call.

        Returns:
            RefinedOutput with the final response and refinement metadata.
        """
        if not self._meta_agent:
            logger.debug("Self-refinement: no meta-agent, returning original")
            return RefinedOutput(
                response=state.get("final_response", ""),
                iterations=0,
                was_improved=False,
            )

        max_iter = max_iterations or self._max_iterations
        current_response = state.get("final_response", "")
        user_input = state.get("user_input", "")
        messages = list(state.get("messages", []))

        quality_scores = []
        improvements = []
        was_improved = False

        for iteration in range(max_iter):
            # Evaluate quality
            assessment = await self._meta_agent.evaluate_response(
                response=current_response,
                original_task=user_input,
                context={
                    "iteration": iteration,
                    "execution_mode": state.get("execution_mode", "react"),
                },
            )

            quality_scores.append(assessment.quality_score)

            # If quality is above threshold, we're done
            if assessment.quality_score >= self._quality_threshold:
                logger.info(
                    f"Self-refinement: quality {assessment.quality_score:.2f} >= "
                    f"threshold {self._quality_threshold:.2f} after {iteration + 1} iterations"
                )
                return RefinedOutput(
                    response=current_response,
                    iterations=iteration + 1,
                    quality_scores=quality_scores,
                    was_improved=was_improved or iteration > 0,
                    final_assessment=assessment,
                    improvements=improvements,
                )

            # If no refinement needed (even though quality is low)
            if not assessment.needs_refinement:
                logger.info(
                    f"Self-refinement: quality {assessment.quality_score:.2f} below threshold "
                    f"but no refinement suggested. Stopping at iteration {iteration + 1}."
                )
                return RefinedOutput(
                    response=current_response,
                    iterations=iteration + 1,
                    quality_scores=quality_scores,
                    was_improved=was_improved,
                    final_assessment=assessment,
                    improvements=improvements,
                )

            # Generate refinement prompt
            refinement_prompt = self._build_refinement_prompt(
                current_response=current_response,
                assessment=assessment,
                iteration=iteration,
            )

            improvements.extend(assessment.improvement_areas)

            # Append refinement prompt to messages
            messages.append({
                "role": "system",
                "content": refinement_prompt,
            })

            # Mark that we've attempted improvement
            was_improved = True

            logger.info(
                f"Self-refinement iteration {iteration + 1}: "
                f"quality={assessment.quality_score:.2f}, "
                f"improving: {', '.join(assessment.improvement_areas[:3])}"
            )

        # Max iterations reached
        logger.info(
            f"Self-refinement: max iterations ({max_iter}) reached, "
            f"final quality={quality_scores[-1]:.2f if quality_scores else 0}"
        )

        return RefinedOutput(
            response=current_response,
            iterations=max_iter,
            quality_scores=quality_scores,
            was_improved=was_improved,
            improvements=improvements,
        )

    def _build_refinement_prompt(
        self,
        current_response: str,
        assessment: QualityAssessment,
        iteration: int,
    ) -> str:
        """Build a refinement prompt based on the quality assessment.

        Args:
            current_response: The current draft response.
            assessment: Quality assessment from meta-agent.
            iteration: Current iteration number.

        Returns:
            Refinement prompt to append to messages.
        """
        areas = ", ".join(assessment.improvement_areas[:3]) if assessment.improvement_areas else "general quality"

        prompt = f"""Your previous response (iteration {iteration + 1}) needs improvement.

Areas to improve: {areas}

Refinement suggestion: {assessment.refinement_prompt}

Please revise your response to address these issues. Focus on making the response more:
- Complete: Address all aspects of the original question
- Accurate: Verify facts and provide correct information
- Clear: Structure the response logically
- Actionable: Provide concrete, useful guidance

Your improved response:"""

        return prompt

    async def save_refinement_experience(
        self,
        memory: Any,
        conversation_id: str,
        output: RefinedOutput,
        original_task: str,
    ) -> None:
        """Save the refinement experience to long-term memory.

        This enables the agent to learn from its refinement history:
        - Episodic: what was refined, how many iterations
        - Strategic: which improvement patterns work

        Args:
            memory: LongTermMemoryManager instance.
            conversation_id: Conversation identifier.
            output: RefinedOutput from the refinement process.
            original_task: The original user task.
        """
        if not memory or not hasattr(memory, "episodic"):
            return

        try:
            # Save episodic memory of the refinement
            outcome = "improved" if output.was_improved else "not_improved"
            summary = (
                f"Self-refinement: {output.iterations} iterations, "
                f"quality scores: {output.quality_scores}, "
                f"outcome: {outcome}, "
                f"improvements: {', '.join(output.improvements[:3])}"
            )

            await memory.episodic.store_episode(
                conversation_id=conversation_id,
                summary=summary,
                outcome=outcome,
                metadata={
                    "type": "self_refinement",
                    "iterations": output.iterations,
                    "quality_scores": output.quality_scores,
                    "improvements": output.improvements[:5],
                    "original_task": original_task[:200],
                },
            )

            # Save strategic memory if refinement was effective
            if output.was_improved and output.quality_scores:
                initial_quality = output.quality_scores[0]
                final_quality = output.quality_scores[-1]
                improvement_delta = final_quality - initial_quality

                if improvement_delta > 0.1:  # Significant improvement
                    await memory.strategic.store_strategy(
                        key=f"refinement_pattern_{len(output.improvements)}areas",
                        content=f"Self-refinement improved quality by {improvement_delta:.2f} "
                                f"({initial_quality:.2f} → {final_quality:.2f}) "
                                f"for {len(output.improvements)} improvement areas: "
                                f"{', '.join(output.improvements[:3])}",
                        category="refinement",
                        source="self_refinement",
                        metadata={
                            "initial_quality": initial_quality,
                            "final_quality": final_quality,
                            "iterations": output.iterations,
                        },
                    )

        except Exception as e:
            logger.warning(f"Failed to save refinement experience: {e}")