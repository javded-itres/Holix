"""Closed-set System One decision. Registered only when the profile turns it on."""

from __future__ import annotations

from typing import Any

from core.tools.base import BaseTool


class SystemOneDecideTool(BaseTool):
    """choice, score, or noul against a configured System One model."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "systemone_decide"
        self.description = (
            "Judge text you already have with a multilingual System One model: "
            "one choice from criteria you supply, a position on a scale you supply, "
            "or the probability a statement is true. "
            "Pass state and criteria in the user's language. "
            "Does not write the reply, code, or a free-form string."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "additionalProperties": False,
            "required": ["state", "questions"],
            "properties": {
                "state": {
                    "description": (
                        "Non-empty string, object, or list to judge. Sent as-is, not translated."
                    ),
                },
                "questions": {
                    "type": "object",
                    "description": (
                        "Map of question id to {type: choice|score|noul, instructions, criteria}. "
                        "choice criteria is an object. score criteria is worst-to-best levels."
                    ),
                },
            },
        }

    async def execute(self, state: Any = None, questions: Any = None, **_: Any) -> str:
        try:
            from core.decision.config import resolve_decision
            from core.decision.systemone import call_systemone
            from core.profile.service import ProfileManager
            from core.tools.execution_context import get_profile_name

            raw = None
            name = str(get_profile_name() or "").strip()
            if name:
                raw = getattr(ProfileManager().load_profile(name), "decision", None)
            return await call_systemone(resolve_decision(raw), state, questions)
        except Exception:
            return "System One error: decision request failed."
