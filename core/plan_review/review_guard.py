"""
Plan Review Guard — manages plan review requests using asyncio.Future + event bus.

Follows the same pattern as ActionGuard in core/security/confirmation.py:
- The graph's plan_review_node creates a Future, emits a PlanReviewRequestEvent,
  and awaits the Future.
- The TUI or API layer resolves the Future by calling resolve_review().
"""

import asyncio
import logging
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class PlanReviewChoice(StrEnum):
    """User choices for plan review."""
    CONFIRM_STEP = "confirm_step"      # Step-by-step: confirm before each step (future enhancement)
    AUTO_EXECUTE = "auto_execute"       # Execute all steps without further confirmation
    REFINE = "refine"                   # Send back to LLM with feedback
    REJECT = "reject"                   # Abort the plan entirely


class PlanReviewGuard:
    """Manages plan review requests using asyncio.Future + event bus.

    The graph's plan_review_node calls request_review() which:
    1. Creates an asyncio.Future
    2. Emits a PlanReviewRequestEvent via the event bus
    3. Awaits the Future (blocking the graph until resolved)

    The TUI or API layer receives the event, shows a modal,
    and calls resolve_review() to set the Future result, unblocking the graph.

    In non-interactive mode, request_review() immediately returns AUTO_EXECUTE.
    """

    def __init__(
        self,
        event_bus: Any | None = None,
        interactive: bool = True,
        review_timeout: int = 600,
    ):
        self._event_bus = event_bus
        self._interactive = interactive
        self._review_timeout = review_timeout

        # Map from review_id -> asyncio.Future[Tuple[PlanReviewChoice, str]]
        self._pending_reviews: dict[str, asyncio.Future] = {}
        self._review_counter = 0

    async def request_review(
        self,
        plan_steps: list[dict[str, Any]],
        conversation_id: str = "default",
        reasoning: str = "",
        user_input: str = "",
        analysis: dict[str, Any] | None = None,
        architecture: dict[str, Any] | None = None,
        rendered_markdown: str = "",
    ) -> tuple[PlanReviewChoice, str]:
        """Emit a PlanReviewRequestEvent and await user decision.

        Creates a Future, emits the event, and blocks until the user
        responds via resolve_review() or the timeout expires.

        Args:
            plan_steps: The list of plan step dicts from plan_node.
            conversation_id: Conversation ID for event correlation.
            reasoning: Brief explanation of the plan order.
            user_input: The original user query.

        Returns:
            Tuple of (PlanReviewChoice, feedback_str).
            In non-interactive mode, returns (AUTO_EXECUTE, "").
            On timeout, returns (AUTO_EXECUTE, "").
        """
        # Non-interactive: auto-execute without prompting
        if not self._interactive:
            logger.info("PlanReviewGuard: non-interactive mode, auto-executing plan")
            return PlanReviewChoice.AUTO_EXECUTE, ""

        self._review_counter += 1
        review_id = f"plan_review_{self._review_counter}_{conversation_id}"

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_reviews[review_id] = future

        logger.info(
            f"PlanReviewGuard: requesting review for plan with {len(plan_steps)} steps "
            f"(id={review_id})"
        )

        try:
            # Emit the event for TUI/API consumption
            if self._event_bus:
                from core.plan_review.review_events import PlanReviewRequestEvent
                event = PlanReviewRequestEvent(
                    review_id=review_id,
                    plan_steps=plan_steps,
                    step_count=len(plan_steps),
                    reasoning=reasoning,
                    user_input=user_input,
                    analysis=analysis,
                    architecture=architecture,
                    rendered_markdown=rendered_markdown,
                    conversation_id=conversation_id,
                )
                self._event_bus.emit(event)
                logger.info(f"PlanReviewGuard: emitted PlanReviewRequestEvent (id={review_id})")

            # Wait for resolution (with configurable timeout)
            timeout = self._review_timeout if self._review_timeout > 0 else None
            logger.info(f"PlanReviewGuard: awaiting review (timeout={timeout}s)")
            result = await asyncio.wait_for(future, timeout=timeout)

            # result is a tuple (PlanReviewChoice, feedback_str)
            if isinstance(result, tuple):
                return result
            # Backward compatibility: if just a PlanReviewChoice
            return result, ""

        except TimeoutError:
            logger.warning(f"PlanReviewGuard: review {review_id} timed out, rejecting plan")
            return PlanReviewChoice.REJECT, ""

        finally:
            self._pending_reviews.pop(review_id, None)

    def resolve_review(
        self,
        review_id: str,
        choice: PlanReviewChoice,
        feedback: str = "",
    ) -> bool:
        """Resolve a pending review request.

        Called by the TUI or API layer when the user responds to
        a plan review prompt. Returns True if successfully resolved,
        False if the ID was not found (e.g., already timed out).

        Args:
            review_id: The ID from PlanReviewRequestEvent.
            choice: The user's choice.
            feedback: Optional refinement feedback.

        Returns:
            True if resolved, False if not found.
        """
        future = self._pending_reviews.get(review_id)
        if future is None or future.done():
            logger.warning(f"PlanReviewGuard: review {review_id} not found or already resolved")
            return False

        future.set_result((choice, feedback))

        logger.info(f"PlanReviewGuard: resolved review {review_id} with choice={choice.value}")

        # Emit response event for logging/UI feedback
        if self._event_bus:
            from core.plan_review.review_events import PlanReviewResponseEvent
            self._event_bus.emit(PlanReviewResponseEvent(
                review_id=review_id,
                choice=choice.value,
                feedback=feedback,
                conversation_id="",
            ))

        return True


# ─── Global instance and init ──────────────────────────────────────────────

_plan_review_guard: PlanReviewGuard | None = None


def init_plan_review_guard(
    event_bus: Any,
    interactive: bool = True,
    review_timeout: int = 600,
) -> PlanReviewGuard:
    """Initialize the global PlanReviewGuard instance.

    Called by HelixAgent after the event bus is ready.
    """
    global _plan_review_guard
    _plan_review_guard = PlanReviewGuard(
        event_bus=event_bus,
        interactive=interactive,
        review_timeout=review_timeout,
    )
    return _plan_review_guard


def get_plan_review_guard() -> PlanReviewGuard | None:
    """Get the global PlanReviewGuard instance (or None if not initialized)."""
    return _plan_review_guard