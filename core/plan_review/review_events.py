"""
Plan Review Events — event types for the plan review flow.

These events integrate with the existing AgentEventBus. They use
string type values that don't collide with the core EventType enum,
and they subclass AgentEvent so they work with bus.emit().

The TUI subscribes to PlanReviewRequestEvent to show a review modal,
and calls PlanReviewGuard.resolve_review() when the user responds.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent_events import AgentEvent, EventType


class PlanReviewEventType:
    """Extension event types for the plan review flow.

    These use string values that don't collide with the core EventType enum,
    and they subclass AgentEvent so they work with AgentEventBus.emit().
    """
    PLAN_REVIEW_REQUEST = "plan_review_request"
    PLAN_REVIEW_RESPONSE = "plan_review_response"


@dataclass
class PlanReviewRequestEvent(AgentEvent):
    """Emitted when a plan has been generated and needs user review.

    The TUI or API layer should display the plan and collect
    a user response, then call PlanReviewGuard.resolve_review().

    The rendered_markdown field contains the full plan formatted as
    Markdown for display in chat. The TUI renders this via rich.markdown.Markdown.

    Attributes:
        review_id: Unique ID for this review request.
        plan_steps: List of step dicts from the plan.
        step_count: Number of steps in the plan.
        reasoning: Brief explanation of the plan order.
        user_input: The original user query that generated this plan.
        analysis: Task analysis dict (task_summary, complexity, clarifying_questions, constraints).
        architecture: Architecture dict (approach, tech_stack, structure, risks).
        rendered_markdown: Pre-rendered Markdown string of the full plan for chat display.
    """
    review_id: str = ""
    plan_steps: List[Dict[str, Any]] = field(default_factory=list)
    step_count: int = 0
    reasoning: str = ""
    user_input: str = ""
    analysis: Optional[Dict[str, Any]] = None
    architecture: Optional[Dict[str, Any]] = None
    rendered_markdown: str = ""

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, 'type', EventType.PLAN_GENERATED)

    def _extra_fields(self) -> Dict[str, Any]:
        return {
            "review_id": self.review_id,
            "plan_steps": self.plan_steps,
            "step_count": self.step_count,
            "reasoning": self.reasoning,
            "user_input": self.user_input,
            "analysis": self.analysis,
            "architecture": self.architecture,
            "rendered_markdown": self.rendered_markdown,
            "event_type": PlanReviewEventType.PLAN_REVIEW_REQUEST,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Override to_dict to use our custom event type string."""
        return {
            "type": PlanReviewEventType.PLAN_REVIEW_REQUEST,
            "timestamp": self.timestamp.isoformat(),
            "conversation_id": self.conversation_id,
            "metadata": self.metadata,
            **self._extra_fields(),
        }


@dataclass
class PlanReviewResponseEvent(AgentEvent):
    """Emitted when the user responds to a plan review request.

    This is informational — it logs what the user decided.
    The actual resolution happens via PlanReviewGuard.resolve_review().

    Attributes:
        review_id: ID matching the original PlanReviewRequestEvent.
        choice: The user's choice ("confirm_step", "auto_execute", "refine", "reject").
        feedback: Optional refinement feedback when choice is "refine".
    """
    review_id: str = ""
    choice: str = ""  # PlanReviewChoice value
    feedback: str = ""

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, 'type', EventType.PLAN_COMPLETED)

    def _extra_fields(self) -> Dict[str, Any]:
        return {
            "review_id": self.review_id,
            "choice": self.choice,
            "feedback": self.feedback,
            "event_type": PlanReviewEventType.PLAN_REVIEW_RESPONSE,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Override to_dict to use our custom event type string."""
        return {
            "type": PlanReviewEventType.PLAN_REVIEW_RESPONSE,
            "timestamp": self.timestamp.isoformat(),
            "conversation_id": self.conversation_id,
            "metadata": self.metadata,
            **self._extra_fields(),
        }