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
            "Ask the human a single clarifying question when you truly cannot "
            "proceed without their decision. The question opens a dialog in the "
            "main Holix UI; when they answer, you receive the reply and continue. "
            "Write the question so a busy human understands it in one glance: "
            "state what you need, offer concrete options when possible, and put "
            "background in `context` (not in the question). Prefer making a "
            "reasonable choice yourself over asking when the task already implies "
            "the answer."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": (
                        "One clear, self-contained question for the human. "
                        "Prefer closed choices when possible, e.g. "
                        "'Use JWT or session cookies for auth?'. "
                        "Do not dump long analysis — put that in context."
                    ),
                },
                "context": {
                    "type": "string",
                    "description": (
                        "Short background: which file/path, what you found, and "
                        "why the choice matters (1–3 sentences)."
                    ),
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