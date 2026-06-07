import json
from typing import Any, Dict, List, Optional

from core.tools.aliases import resolve_tool_name
from core.tools.base import BaseTool


class ToolRegistry:
    """Registry for managing and executing agent tools."""

    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self._action_guard = None  # Set by set_action_guard()

    def set_action_guard(self, guard) -> None:
        """Set the ActionGuard instance for pre-execution confirmation.

        When installed, all tool executions go through the guard's
        check_and_execute() method which classifies risk and may
        request confirmation before executing.

        Args:
            guard: An ActionGuard instance, or None to disable.
        """
        self._action_guard = guard

    def register(self, tool: BaseTool) -> None:
        """Register a tool in the registry.

        Args:
            tool: Tool instance to register.
        """
        self.tools[tool.name] = tool
        # Note: we no longer print here. The agent loop or higher level
        # can emit AgentEvent if it wants to surface tool registration.

    def register_alias(self, alias: str, tool: BaseTool) -> None:
        """Register an alternate name for an existing tool."""
        self.tools[alias] = tool

    def register_all(self) -> None:
        """Import and register all available tools."""
        from core.tools.terminal import TerminalTool
        from core.tools.file_ops import ReadFileTool, WriteFileTool, ListDirectoryTool
        from core.tools.web_search import WebSearchTool, WebFetchTool
        from core.tools.database import SQLQueryTool, SQLSchemaTool
        from core.tools.code_executor import PythonExecutorTool, MathCalculatorTool
        from core.tools.ask_user import AskUserTool

        # File operations
        self.register(ReadFileTool())
        self.register(WriteFileTool())

        # System
        self.register(TerminalTool())

        # Web
        self.register(WebSearchTool())
        fetch_tool = WebFetchTool()
        self.register(fetch_tool)
        self.register_alias("web_fetch", fetch_tool)

        # Database
        self.register(SQLQueryTool())
        self.register(SQLSchemaTool())

        # Code execution
        self.register(PythonExecutorTool())
        self.register(MathCalculatorTool())

        # Sub-agent ↔ user bridge
        self.register(AskUserTool())

        from config import settings

        if settings.enable_browser_tools:
            from core.tools.browser import register_browser_tools

            register_browser_tools(self)

    async def register_mcp(self, mcp_servers: Dict[str, Any], assignments: Optional[Dict[str, List[str]]] = None, slot: str = "main") -> int:
        """Dynamically register MCP tools for this registry (called from agent init).

        Returns number of tools registered.
        """
        if not mcp_servers:
            return 0
        try:
            from core.mcp.manager import MCPManager
            mgr = MCPManager(mcp_servers)
            await mgr.connect_all()
            enabled = []
            if assignments and slot in assignments:
                enabled = assignments[slot]
            elif assignments:
                enabled = list(assignments.get("main", mcp_servers.keys()))
            else:
                enabled = list(mcp_servers.keys())
            # Give slow stdio servers (npx/uvx downloads, Context7 auth, etc.) time to initialize + list_tools
            try:
                await mgr.wait_ready(enabled or None, timeout=10.0)
            except Exception:
                pass
            tools = mgr.get_tool_adapters(enabled or None)
            for t in tools:
                self.register(t)
            # keep ref on registry for shutdown if needed
            self._mcp_manager = mgr  # type: ignore[attr-defined]
            return len(tools)
        except Exception as exc:
            # do not break agent if MCP misconfigured
            print(f"Warning: MCP registration skipped: {exc}")
            return 0

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Get OpenAI-compatible schemas for all registered tools.

        Returns:
            List of tool schemas
        """
        return [tool.to_openai_schema() for tool in self.tools.values()]

    async def execute(self, tool_call, conversation_id: str = "default") -> str:
        """Execute a tool call from the LLM.

        If an ActionGuard is installed, all tool executions go through
        check_and_execute() which classifies risk and may request
        user confirmation before executing.

        Args:
            tool_call: OpenAI tool call object
            conversation_id: Conversation ID for event correlation.

        Returns:
            str: Result of tool execution

        Raises:
            ValueError: If tool is not found
        """
        tool_name = tool_call.function.name
        resolved = resolve_tool_name(tool_name)

        if resolved not in self.tools:
            return f"Error: Tool '{tool_name}' not found"

        tool = self.tools[resolved]

        try:
            args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON arguments - {e}"

        from core.tools.execution_context import conversation_scope, reset_conversation_scope

        token = conversation_scope(conversation_id)
        try:
            # Gate with ActionGuard if installed
            if self._action_guard:
                result = await self._action_guard.check_and_execute(
                    tool_name=tool_name,
                    tool_instance=tool,
                    arguments=args,
                    execute_fn=tool.execute,
                    conversation_id=conversation_id,
                )
                return result

            # No guard: execute directly (backward compatible)
            try:
                return await tool.execute(**args)
            except Exception as e:
                return f"Error executing {tool_name}: {str(e)}"
        finally:
            reset_conversation_scope(token)

    def get_tool_names(self) -> List[str]:
        """Get names of all registered tools.

        Returns:
            List of tool names
        """
        return list(self.tools.keys())