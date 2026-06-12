"""
Tool Bridge — wraps Holix BaseTool instances as LangChain StructuredTool
for use within LangGraph nodes.
"""

import logging
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, create_model

from core.tools.base import BaseTool
from core.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def _schema_to_pydantic(openai_schema: dict[str, Any]) -> type[BaseModel]:
    """Convert an OpenAI function schema to a Pydantic model.

    LangChain StructuredTool requires a Pydantic model as args_schema.
    This converts the OpenAI-style parameter schema that Holix tools
    already produce via to_openai_schema().

    Args:
        openai_schema: OpenAI function parameters schema dict.

    Returns:
        A Pydantic model class matching the schema.
    """
    properties = openai_schema.get("properties", {})
    required = set(openai_schema.get("required", []))

    field_definitions = {}
    type_map = {
        "string": (str, ...),
        "integer": (int, ...),
        "number": (float, ...),
        "boolean": (bool, ...),
        "array": (list, ...),
        "object": (dict, ...),
    }

    for prop_name, prop_schema in properties.items():
        prop_type = prop_schema.get("type", "string")
        description = prop_schema.get("description", "")
        default = prop_schema.get("default")

        if prop_name in required:
            if prop_type in type_map:
                field_definitions[prop_name] = (
                    type_map[prop_type][0],
                    description,
                )
            else:
                field_definitions[prop_name] = (str, description)
        else:
            if prop_type in type_map:
                python_type = type_map[prop_type][0]
            else:
                python_type = str

            if default is not None:
                field_definitions[prop_name] = (python_type, default)
            else:
                field_definitions[prop_name] = (python_type | None, None)

    # Create a dynamic Pydantic model
    if field_definitions:
        model = create_model("ToolArgs", **field_definitions)
    else:
        model = create_model("ToolArgs")

    return model


def wrap_holix_tool(holix_tool: BaseTool) -> StructuredTool:
    """Wrap a Holix BaseTool as a LangChain StructuredTool.

    This bridge allows Holix's existing tool system to work seamlessly
    within LangGraph nodes. The tool's execute() method is called
    directly — no LangChain agent infrastructure required.

    Args:
        holix_tool: A Holix BaseTool instance.

    Returns:
        A LangChain StructuredTool wrapping the Holix tool.
    """
    openai_schema = holix_tool.to_openai_schema()
    function_schema = openai_schema.get("function", {})

    # Build Pydantic args_schema from OpenAI parameters
    parameters = function_schema.get("parameters", {})
    args_schema = _schema_to_pydantic(parameters) if parameters else None

    async def _arun(**kwargs) -> str:
        """Async executor that delegates to the Holix tool."""
        return await holix_tool.execute(**kwargs)

    def _run(**kwargs) -> str:
        """Sync executor — raises error since Holix tools are async."""
        raise NotImplementedError(
            f"Tool '{holix_tool.name}' only supports async execution. "
            "Use the async interface."
        )

    return StructuredTool.from_function(
        coroutine=_arun,
        func=_run,
        name=holix_tool.name,
        description=holix_tool.description or function_schema.get("description", ""),
        args_schema=args_schema,
    )


def wrap_all_tools(registry: ToolRegistry) -> list[StructuredTool]:
    """Wrap all registered Holix tools as LangChain StructuredTools.

    Args:
        registry: The Holix ToolRegistry instance.

    Returns:
        List of LangChain StructuredTool instances.
    """
    lc_tools = []
    for holix_tool in registry.tools.values():
        try:
            lc_tool = wrap_holix_tool(holix_tool)
            lc_tools.append(lc_tool)
        except Exception as e:
            logger.warning(f"Failed to wrap tool '{holix_tool.name}': {e}")

    return lc_tools


def unwrap_langchain_tool(lc_tool: StructuredTool) -> BaseTool:
    """Create a Holix BaseTool adapter from a LangChain StructuredTool.

    This reverse bridge allows LangChain-native tools to be used
    within Holix's ToolRegistry.

    Args:
        lc_tool: A LangChain StructuredTool instance.

    Returns:
        A Holix BaseTool adapter.
    """

    class LangChainToolAdapter(BaseTool):
        """Adapts a LangChain StructuredTool to the Holix BaseTool interface."""

        def __init__(self, lc: StructuredTool):
            super().__init__()
            self.name = lc.name
            self.description = lc.description or ""
            self._lc_tool = lc

            # Convert Pydantic args_schema to OpenAI format
            if lc.args_schema:
                schema = lc.args_schema.model_json_schema()
                self.parameters = {
                    "type": "object",
                    "properties": schema.get("properties", {}),
                    "required": schema.get("required", []),
                }
            else:
                self.parameters = {"type": "object", "properties": {}}

        async def execute(self, **kwargs) -> str:
            """Execute the wrapped LangChain tool."""
            if self._lc_tool.coroutine:
                return await self._lc_tool.coroutine(**kwargs)
            elif self._lc_tool.func:
                return self._lc_tool.func(**kwargs)
            else:
                return f"Error: Tool '{self.name}' has no executor"

    return LangChainToolAdapter(lc_tool)