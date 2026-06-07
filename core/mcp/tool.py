"""MCPTool — BaseTool adapter for a single tool exposed by an MCP server."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict

from core.tools.base import BaseTool

if TYPE_CHECKING:
    from core.mcp.manager import MCPManager


class MCPTool(BaseTool):
    """Adapter that turns an MCP tool definition into a Helix BaseTool.

    The actual invocation is delegated to MCPManager (which owns the live
    ClientSession(s)). This keeps the tool stateless from the registry POV.
    """

    def __init__(
        self,
        *,
        server_name: str,
        tool_name: str,
        description: str,
        input_schema: Dict[str, Any],
        manager: "MCPManager",
        risk_level: str = "medium",
    ) -> None:
        super().__init__()
        self.server_name = server_name
        self.tool_name = tool_name  # original MCP name
        self.name = f"mcp_{server_name}_{tool_name}"  # unique, safe for LLM
        self.description = description or f"MCP tool '{tool_name}' from server '{server_name}'"
        self.parameters = input_schema or {"type": "object", "properties": {}}
        self.risk_level = risk_level
        self._manager = manager

    async def execute(self, **kwargs: Any) -> str:
        """Delegate to the MCP session via manager. Always returns str (error strings on failure)."""
        try:
            result = await self._manager.call_tool(self.server_name, self.tool_name, kwargs)
            # MCP result is usually list of content items; normalize to text
            if isinstance(result, dict):
                # Some servers return structured
                if "content" in result:
                    parts = []
                    for c in result["content"]:
                        if isinstance(c, dict) and c.get("type") == "text":
                            parts.append(c.get("text", ""))
                        else:
                            parts.append(str(c))
                    return "\n".join(parts) or json.dumps(result, ensure_ascii=False)[:4000]
                return json.dumps(result, ensure_ascii=False)[:4000]
            if isinstance(result, (list, tuple)):
                return "\n".join(str(x) for x in result)
            return str(result)[:8000]
        except Exception as exc:
            # Surface the inner error from the MCP server (e.g. backend API failures like 525)
            # The full tool name is already known to the caller/LLM.
            return f"Error from MCP server '{self.server_name}' (tool {self.tool_name}): {exc}"
