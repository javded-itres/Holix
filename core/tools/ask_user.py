"""Tool for sub-agents to ask the user a question in the main chat stream."""

from __future__ import annotations

from typing import Any

from core.tools.base import BaseTool
from core.tools.execution_context import get_interaction_bridge, get_subagent_name


class AskUserTool(BaseTool):
    """Pause a sub-agent and surface a question to the main chat."""

    def __init__(self):
        super().__init__()
        self.name = "ask_user"
        self.description = (
            "Ask the user a clarifying question. The question appears in the main "
            "chat; when the user answers, you receive the reply and can continue."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Clear question for the user",
                },
                "context": {
                    "type": "string",
                    "description": "Optional short context (what you are doing)",
                },
            },
            "required": ["question"],
        }

    async def execute(self, question: str, context: str = "", **_: Any) -> str:
        subagent_name = get_subagent_name()
        if not subagent_name:
            return (
                "Error: ask_user is only available while running as a sub-agent. "
                "Ask the user directly in your reply instead."
            )

        bridge = get_interaction_bridge()
        if bridge is None:
            return "Error: sub-agent interaction bridge is not available"

        return await bridge.ask_user(
            subagent_name,
            question.strip(),
            context=(context or "").strip(),
        )