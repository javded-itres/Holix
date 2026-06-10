"""
Confirmation Events — event types for the dangerous action confirmation flow.

These events integrate with the existing AgentEventBus. They use
string type values that don't collide with the core EventType enum,
and they subclass AgentEvent so they work with bus.emit().

The TUI subscribes to ConfirmationRequestEvent to show a confirmation
prompt, and calls ActionGuard.resolve_confirmation() when the user
responds.
"""

from dataclasses import dataclass, field
from typing import Any

from core.agent_events import AgentEvent, EventType


class ConfirmationEventType:
    """Extension event types for the confirmation flow.

    These use string values that don't collide with the core EventType enum,
    and they subclass AgentEvent so they work with AgentEventBus.emit().
    """
    CONFIRMATION_REQUEST = "confirmation_request"
    CONFIRMATION_RESPONSE = "confirmation_response"


@dataclass
class ConfirmationRequestEvent(AgentEvent):
    """Emitted when a tool call requires user confirmation.

    The TUI or API layer should display this prompt and collect
    a user response, then call action_guard.resolve_confirmation().

    Attributes:
        confirmation_id: Unique ID for this confirmation request.
        tool_name: Name of the tool that needs confirmation.
        arguments: The arguments that will be passed to the tool.
        risk_level: Risk level string ("no", "low", "medium", "high").
        reason: Human-readable explanation of why confirmation is needed.
        pattern_matched: Optional pattern that triggered the risk escalation.
    """
    confirmation_id: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    risk_level: str = ""  # RiskLevel value string
    reason: str = ""
    pattern_matched: str | None = None
    subagent_name: str = ""

    def __post_init__(self):
        # Use a valid EventType as the base, then override the display
        object.__setattr__(self, 'type', EventType.ERROR)  # Will be overridden below

    def _extra_fields(self) -> dict[str, Any]:
        return {
            "confirmation_id": self.confirmation_id,
            "tool_name": self.tool_name,
            "risk_level": self.risk_level,
            "reason": self.reason,
            "pattern_matched": self.pattern_matched,
            "subagent_name": self.subagent_name,
            "event_type": ConfirmationEventType.CONFIRMATION_REQUEST,
        }

    def to_dict(self) -> dict[str, Any]:
        """Override to_dict to use our custom event type string."""
        return {
            "type": ConfirmationEventType.CONFIRMATION_REQUEST,
            "timestamp": self.timestamp.isoformat(),
            "conversation_id": self.conversation_id,
            "metadata": self.metadata,
            **self._extra_fields(),
        }


@dataclass
class ConfirmationResponseEvent(AgentEvent):
    """Emitted when the user responds to a confirmation request.

    This is informational — it logs what the user decided.
    The actual resolution happens via ActionGuard.resolve_confirmation().

    Attributes:
        confirmation_id: ID matching the original ConfirmationRequestEvent.
        choice: The user's choice ("allow_once", "allow_session", "allow_always", "deny").
        tool_name: Name of the tool (for logging convenience).
        risk_level: Risk level of the original request.
    """
    confirmation_id: str = ""
    choice: str = ""  # ConfirmationChoice value
    tool_name: str = ""
    risk_level: str = ""

    def __post_init__(self):
        object.__setattr__(self, 'type', EventType.ERROR)

    def _extra_fields(self) -> dict[str, Any]:
        return {
            "confirmation_id": self.confirmation_id,
            "choice": self.choice,
            "tool_name": self.tool_name,
            "risk_level": self.risk_level,
            "event_type": ConfirmationEventType.CONFIRMATION_RESPONSE,
        }

    def to_dict(self) -> dict[str, Any]:
        """Override to_dict to use our custom event type string."""
        return {
            "type": ConfirmationEventType.CONFIRMATION_RESPONSE,
            "timestamp": self.timestamp.isoformat(),
            "conversation_id": self.conversation_id,
            "metadata": self.metadata,
            **self._extra_fields(),
        }