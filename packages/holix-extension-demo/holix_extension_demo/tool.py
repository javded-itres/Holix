"""Demo tool registered by the agent extension."""

from __future__ import annotations

from typing import Any

from core.tools.base import BaseTool


class DemoEchoTool(BaseTool):
    def __init__(self) -> None:
        super().__init__()
        self.name = "demo_echo"
        self.description = "Echo text back (Holix extension demo tool)."
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to echo",
                }
            },
            "required": ["text"],
        }

    async def execute(self, text: str, **kwargs: Any) -> str:
        return f"[demo_echo] {text}"