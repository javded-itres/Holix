"""Run a one-shot prompt against an ACP coding agent."""

from __future__ import annotations

from typing import Any

from core.acp.client import AcpError, run_acp_prompt
from core.acp.config import acp_argv
from core.tools.base import BaseTool


class RunAcpAgentTool(BaseTool):
    """Drive an out-of-process Agent Client Protocol (ACP) child."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "run_acp_agent"
        self.description = (
            "Run a task on an external ACP coding agent (stdio JSON-RPC). "
            "Requires HOLIX_ACP_COMMAND (e.g. `grok --acp`, `claude --acp`). "
            "Fresh session, no parent history. Permission prompts are auto-answered "
            "(HOLIX_ACP_PERMISSION=reject|allow)."
        )
        self.risk_level = "high"
        self.parameters = {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Task for the ACP agent",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (default: workspace)",
                },
                "command": {
                    "type": "string",
                    "description": "Override HOLIX_ACP_COMMAND for this call",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 300)",
                    "default": 300,
                },
            },
            "required": ["prompt"],
        }

    async def execute(
        self,
        prompt: str,
        cwd: str = "",
        command: str = "",
        timeout: int = 300,
        **_: Any,
    ) -> str:
        text = (prompt or "").strip()
        if not text:
            return "Error: prompt is empty"
        if not acp_argv(command=command or None):
            return (
                "Error: no ACP agent configured. Set HOLIX_ACP_COMMAND "
                "to an ACP stdio binary (example: grok --acp)."
            )
        work = (cwd or "").strip() or None
        if work is None:
            try:
                from core.workspace import get_configured_workspace_root

                root = get_configured_workspace_root()
                work = str(root) if root is not None else None
            except Exception:
                work = None
        try:
            result = await run_acp_prompt(
                text,
                cwd=work,
                command=command or None,
                timeout=float(timeout or 300),
            )
        except AcpError as exc:
            return f"Error: {exc}"
        body = result.text or "(no assistant text)"
        return f"ACP stop={result.stop_reason} session={result.session_id or '—'}\n{body}"
