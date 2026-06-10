"""Events for sub-agent questions surfaced in the main chat stream."""

from dataclasses import dataclass
from typing import Any

from core.agent_events import AgentEvent, EventType


class SubAgentInteractionEventType:
    QUESTION = "subagent_question"


@dataclass
class SubAgentQuestionEvent(AgentEvent):
    """Emitted when a sub-agent needs an answer from the user."""

    request_id: str = ""
    subagent_name: str = ""
    question: str = ""
    context: str = ""

    def __post_init__(self):
        object.__setattr__(self, "type", EventType.ERROR)

    def _extra_fields(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "subagent_name": self.subagent_name,
            "question": self.question,
            "context": self.context,
            "event_type": SubAgentInteractionEventType.QUESTION,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": SubAgentInteractionEventType.QUESTION,
            "timestamp": self.timestamp.isoformat(),
            "conversation_id": self.conversation_id,
            "metadata": self.metadata,
            **self._extra_fields(),
        }