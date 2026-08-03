"""
Plan Review Guard — manages plan review requests using asyncio.Future + event bus.

Follows the same pattern as ActionGuard in core/security/confirmation.py:
- The graph's plan_review_node creates a Future, emits a PlanReviewRequestEvent,
  and awaits the Future.
- The TUI or API layer resolves the Future by calling resolve_review().

Pending reviews are also registered in a process-wide map so Studio / hosts can
resolve them even when multiple HolixAgent instances exist (one per tab).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class PlanReviewChoice(StrEnum):
    """User choices for plan review."""

    CONFIRM_STEP = "confirm_step"  # Proceed with execution (saved as confirmed)
    AUTO_EXECUTE = "auto_execute"  # Execute all steps without further confirmation
    REFINE = "refine"  # Send back to LLM with feedback
    REJECT = "reject"  # Abort the plan entirely
    PROCEED_ASSUMPTIONS = "proceed_assumptions"  # Skip open questions, show plan anyway


# Process-wide pending futures: review_id -> Future
# Allows resolve from any host even if agent/guard identity is ambiguous.
_GLOBAL_PENDING: dict[str, asyncio.Future] = {}
_GLOBAL_LOCK = threading.RLock()


def _register_global_pending(review_id: str, future: asyncio.Future) -> None:
    with _GLOBAL_LOCK:
        _GLOBAL_PENDING[review_id] = future


def _unregister_global_pending(review_id: str) -> None:
    with _GLOBAL_LOCK:
        _GLOBAL_PENDING.pop(review_id, None)


def list_global_pending_review_ids() -> list[str]:
    with _GLOBAL_LOCK:
        return list(_GLOBAL_PENDING.keys())


def _set_future_result(future: asyncio.Future, result: Any) -> bool:
    """Set Future result on the correct event loop (thread-safe when needed)."""
    if future.done():
        return False
    try:
        loop = future.get_loop()
    except Exception:
        loop = None

    def _apply() -> None:
        if not future.done():
            future.set_result(result)

    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    if loop is not None and loop.is_running() and running is not loop:
        loop.call_soon_threadsafe(_apply)
        return True
    _apply()
    return True


def resolve_global_pending_review(
    review_id: str,
    choice: PlanReviewChoice,
    feedback: str = "",
) -> bool:
    """Resolve a pending review by id, or the only pending review if id is empty/stale."""
    rid = (review_id or "").strip()
    with _GLOBAL_LOCK:
        pending = dict(_GLOBAL_PENDING)

    if rid and rid in pending:
        ok = _set_future_result(pending[rid], (choice, feedback))
        if ok:
            logger.info(
                "PlanReviewGuard: global resolve id=%s choice=%s",
                rid,
                choice.value,
            )
        return ok

    # Single in-flight review → accept even if UI review_id drifted.
    if len(pending) == 1:
        only_id, fut = next(iter(pending.items()))
        ok = _set_future_result(fut, (choice, feedback))
        if ok:
            logger.info(
                "PlanReviewGuard: global resolve sole pending id=%s (requested=%s) choice=%s",
                only_id,
                rid or "∅",
                choice.value,
            )
        return ok

    if rid:
        logger.warning(
            "PlanReviewGuard: global pending miss id=%s open=%s",
            rid,
            list(pending.keys()),
        )
    return False


def reject_all_global_pending_reviews(*, feedback: str = "stopped by user") -> int:
    """Reject every process-wide pending plan review (Stop / shutdown)."""
    with _GLOBAL_LOCK:
        items = list(_GLOBAL_PENDING.items())
    n = 0
    for rid, fut in items:
        if _set_future_result(fut, (PlanReviewChoice.REJECT, feedback)):
            n += 1
            logger.info("PlanReviewGuard: rejected pending id=%s (%s)", rid, feedback)
    return n


def reject_global_pending_reviews_for_conversation(
    conversation_id: str,
    *,
    feedback: str = "stopped by user",
) -> int:
    """Reject pending plan reviews whose review_id is bound to *conversation_id*.

    Review ids are ``plan_review_{n}_{conversation_id}`` (see request_review).
    Other tabs' plan reviews stay open.
    """
    cid = (conversation_id or "").strip()
    if not cid:
        return 0
    suffix = f"_{cid}"
    with _GLOBAL_LOCK:
        items = list(_GLOBAL_PENDING.items())
    n = 0
    for rid, fut in items:
        rid_s = str(rid or "")
        if rid_s == cid or rid_s.endswith(suffix) or f"_{cid}_" in rid_s:
            if _set_future_result(fut, (PlanReviewChoice.REJECT, feedback)):
                n += 1
                logger.info(
                    "PlanReviewGuard: rejected pending id=%s for conversation=%s (%s)",
                    rid,
                    cid,
                    feedback,
                )
    return n


class PlanReviewGuard:
    """Manages plan review requests using asyncio.Future + event bus.

    The graph's plan_review_node calls request_review() which:
    1. Creates an asyncio.Future
    2. Emits a PlanReviewRequestEvent via the event bus
    3. Awaits the Future (blocking the graph until resolved)

    The TUI or API layer receives the event, shows a modal,
    and calls resolve_review() to set the Future result, unblocking the graph.

    In non-interactive mode, request_review() immediately returns AUTO_EXECUTE.

    review_timeout:
      - > 0: wait at most N seconds, then REJECT (safe default for unattended runs)
      - 0 or negative: wait indefinitely until user responds (Studio / interactive TUI)
    """

    def __init__(
        self,
        event_bus: Any | None = None,
        interactive: bool = True,
        review_timeout: int = 0,
    ):
        self._event_bus = event_bus
        self._interactive = interactive
        self._review_timeout = int(review_timeout or 0)

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
        phase: str = "approval",
        clarifying_questions: list[str] | None = None,
    ) -> tuple[PlanReviewChoice, str]:
        """Emit a PlanReviewRequestEvent and await user decision.

        Creates a Future, emits the event, and blocks until the user
        responds via resolve_review() or (if configured) the timeout expires.

        Returns:
            Tuple of (PlanReviewChoice, feedback_str).
            In non-interactive mode, returns (AUTO_EXECUTE, "").
            On timeout (only when review_timeout > 0), returns (REJECT, "").
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
        _register_global_pending(review_id, future)

        logger.info(
            "PlanReviewGuard: requesting review for plan with %s steps (id=%s timeout=%s)",
            len(plan_steps),
            review_id,
            self._review_timeout if self._review_timeout > 0 else "∞",
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
                    phase=phase,
                    clarifying_questions=clarifying_questions or [],
                )
                self._event_bus.emit(event)
                logger.info(
                    "PlanReviewGuard: emitted PlanReviewRequestEvent (id=%s)", review_id
                )

            # 0 / negative = wait forever for explicit user confirmation
            timeout = self._review_timeout if self._review_timeout > 0 else None
            logger.info(
                "PlanReviewGuard: awaiting review id=%s timeout=%s",
                review_id,
                timeout if timeout is not None else "∞",
            )
            result = await asyncio.wait_for(future, timeout=timeout)

            # result is a tuple (PlanReviewChoice, feedback_str)
            if isinstance(result, tuple):
                return result
            # Backward compatibility: if just a PlanReviewChoice
            return result, ""

        except TimeoutError:
            logger.warning(
                "PlanReviewGuard: review %s timed out after %ss, rejecting plan",
                review_id,
                self._review_timeout,
            )
            return PlanReviewChoice.REJECT, "plan review timed out"
        except asyncio.CancelledError:
            logger.info("PlanReviewGuard: review %s cancelled (stop)", review_id)
            raise

        finally:
            self._pending_reviews.pop(review_id, None)
            _unregister_global_pending(review_id)

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
        """
        rid = (review_id or "").strip()
        future = self._pending_reviews.get(rid) if rid else None
        if future is None or future.done():
            # Fall back to process-wide map (other agent instance may own the Future)
            if resolve_global_pending_review(rid, choice, feedback):
                self._emit_response(rid, choice, feedback)
                return True
            # Sole local pending
            if len(self._pending_reviews) == 1:
                only_id, only_fut = next(iter(self._pending_reviews.items()))
                if _set_future_result(only_fut, (choice, feedback)):
                    logger.info(
                        "PlanReviewGuard: resolved sole local pending id=%s (requested=%s)",
                        only_id,
                        rid or "∅",
                    )
                    self._emit_response(only_id, choice, feedback)
                    return True
            logger.warning(
                "PlanReviewGuard: review %s not found or already resolved (local=%s global=%s)",
                rid or "∅",
                list(self._pending_reviews.keys()),
                list_global_pending_review_ids(),
            )
            return False

        if not _set_future_result(future, (choice, feedback)):
            return False

        logger.info(
            "PlanReviewGuard: resolved review %s with choice=%s", rid, choice.value
        )
        self._emit_response(rid, choice, feedback)
        return True

    def _emit_response(
        self, review_id: str, choice: PlanReviewChoice, feedback: str
    ) -> None:
        if not self._event_bus:
            return
        try:
            from core.plan_review.review_events import PlanReviewResponseEvent

            self._event_bus.emit(
                PlanReviewResponseEvent(
                    review_id=review_id or "",
                    choice=choice.value,
                    feedback=feedback,
                    conversation_id="",
                )
            )
        except Exception:
            logger.debug("PlanReviewGuard: response event emit failed", exc_info=True)


# ─── Global instance and init ──────────────────────────────────────────────

_plan_review_guard: PlanReviewGuard | None = None


def build_plan_review_guard(
    event_bus: Any,
    interactive: bool = True,
    review_timeout: int = 0,
) -> PlanReviewGuard:
    """Construct a PlanReviewGuard for one agent instance."""
    return PlanReviewGuard(
        event_bus=event_bus,
        interactive=interactive,
        review_timeout=review_timeout,
    )


def init_plan_review_guard(
    event_bus: Any,
    interactive: bool = True,
    review_timeout: int = 0,
) -> PlanReviewGuard:
    """Initialize and register the global PlanReviewGuard (legacy compat)."""
    global _plan_review_guard
    _plan_review_guard = build_plan_review_guard(
        event_bus=event_bus,
        interactive=interactive,
        review_timeout=review_timeout,
    )
    return _plan_review_guard


def get_plan_review_guard(profile_name: str | None = None) -> PlanReviewGuard | None:
    """Get PlanReviewGuard from live agent session or global fallback."""
    from core.runtime.agent_sessions import get_agent_attribute

    agent_guard = get_agent_attribute(profile_name, "_plan_review_guard")
    if agent_guard is not None:
        return agent_guard
    return _plan_review_guard


def resolve_plan_review_guard(agent: Any | None = None) -> PlanReviewGuard | None:
    """Resolve PlanReviewGuard for graph nodes and channel hosts.

    Prefer the guard attached to the *current* agent instance (Studio multi-tab,
    Telegram/MAX hosts). Fall back to the profile session registry, then the
    legacy process-global guard.
    """
    if agent is not None:
        guard = getattr(agent, "_plan_review_guard", None)
        if guard is not None:
            return guard
        try:
            from core.profile.soul import profile_name_from_agent

            profile = profile_name_from_agent(agent)
        except Exception:
            profile = getattr(getattr(agent, "config", None), "profile_name", None)
        resolved = get_plan_review_guard(profile)
        if resolved is not None:
            return resolved
    return get_plan_review_guard()
