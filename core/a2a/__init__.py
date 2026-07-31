"""Agent2Agent (A2A) protocol support for Holix.

Holix can act as:
- **A2A Server** — expose the profile agent via gateway (Agent Card + message/send)
- **A2A Client** — call remote A2A agents via tools (a2a_discover, a2a_send_message, …)

Protocol: https://a2a-protocol.org (JSON-RPC + Agent Card discovery).
"""

from core.a2a.card import build_agent_card
from core.a2a.client import A2AClient, A2AClientError
from core.a2a.config import A2AConfig, load_a2a_config
from core.a2a.models import A2AMessage, A2APart, A2ATask, TaskState

__all__ = [
    "A2AClient",
    "A2AClientError",
    "A2AConfig",
    "A2AMessage",
    "A2APart",
    "A2ATask",
    "TaskState",
    "build_agent_card",
    "load_a2a_config",
]
