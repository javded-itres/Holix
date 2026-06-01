import json
from typing import Dict, List, Any

from core.tools.base import BaseTool


class ToolRegistry:
    """Registry for managing and executing agent tools."""

    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool in the registry.

        Args:
            tool: Tool instance to register
        """
        self.tools[tool.name] = tool
        print(f"Registered tool: {tool.name}")

    def register_all(self) -> None:
        """Import and register all available tools."""
        from core.tools.terminal import TerminalTool
        from core.tools.file_ops import ReadFileTool, WriteFileTool, ListDirectoryTool
        from core.tools.web_search import WebSearchTool, WebFetchTool
        from core.tools.database import SQLQueryTool, SQLSchemaTool
        from core.tools.code_executor import PythonExecutorTool, MathCalculatorTool

        # File operations
        self.register(ReadFileTool())
        self.register(WriteFileTool())
        self.register(ListDirectoryTool())

        # System
        self.register(TerminalTool())

        # Web
        self.register(WebSearchTool())
        self.register(WebFetchTool())

        # Database
        self.register(SQLQueryTool())
        self.register(SQLSchemaTool())

        # Code execution
        self.register(PythonExecutorTool())
        self.register(MathCalculatorTool())

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Get OpenAI-compatible schemas for all registered tools.

        Returns:
            List of tool schemas
        """
        return [tool.to_openai_schema() for tool in self.tools.values()]

    async def execute(self, tool_call) -> str:
        """Execute a tool call from the LLM.

        Args:
            tool_call: OpenAI tool call object

        Returns:
            str: Result of tool execution

        Raises:
            ValueError: If tool is not found
        """
        tool_name = tool_call.function.name

        if tool_name not in self.tools:
            return f"Error: Tool '{tool_name}' not found"

        tool = self.tools[tool_name]

        try:
            args = json.loads(tool_call.function.arguments)
            result = await tool.execute(**args)
            return result
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON arguments - {e}"
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    def get_tool_names(self) -> List[str]:
        """Get names of all registered tools.

        Returns:
            List of tool names
        """
        return list(self.tools.keys())
