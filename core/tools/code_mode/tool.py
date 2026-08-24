"""``run_code`` — Code mode transport tool."""

from __future__ import annotations

from typing import Any

from core.tools.base import BaseTool
from core.tools.code_mode.bridge import run_code_program
from core.tools.code_mode.policy import RUN_CODE_NAME
from core.tools.execution_context import get_conversation_id, get_tools_registry


class RunCodeTool(BaseTool):
    """Run a Python program that calls Holix tools through the generated SDK."""

    def __init__(self, registry: Any | None = None) -> None:
        super().__init__()
        self.name = RUN_CODE_NAME
        self.description = (
            "Run a Python program against the workspace tools SDK. "
            "Pass the function body in `code` and a short `description`. "
            "Call tools as tools.name(arg=value). Only print() and return values "
            "come back to you — not intermediate tool dumps."
        )
        self.risk_level = "high"
        self.parameters = {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python function body that uses tools.*",
                },
                "description": {
                    "type": "string",
                    "description": "Short summary of what the program does",
                },
            },
            "required": ["code", "description"],
        }
        self._registry = registry

    async def execute(self, code: str, description: str = "", timeout: int | None = None) -> str:
        if not str(code or "").strip():
            return "Error: Invalid JSON arguments — `code` is required"
        if not str(description or "").strip():
            return "Error: Invalid JSON arguments — `description` is required"
        registry = get_tools_registry() or self._registry
        if registry is None:
            return "Error: run_code has no tool registry"
        timeout_s = None
        if timeout is not None:
            from core.tools.code_mode.policy import clamp_wall_timeout_s

            timeout_s = clamp_wall_timeout_s(timeout)
        conversation_id = get_conversation_id()
        memory = None
        try:
            from core.tools.execution_context import get_memory_facade

            memory = get_memory_facade()
        except Exception:
            memory = None
        return await run_code_program(
            registry,
            code=code,
            description=description,
            conversation_id=conversation_id,
            timeout_s=timeout_s,
            memory=memory,
            parent_tool_id=RUN_CODE_NAME,
        )
