import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from core.tools.aliases import remap_tool_arguments


def filter_execute_kwargs(
    execute_fn: Callable[..., Any], arguments: dict[str, Any] | None
) -> dict[str, Any]:
    """Adapt foreign arg names, then drop keys ``execute`` does not accept.

    Qwen often copies ``project_key`` onto every Studio tool. Without this,
    ``execute()`` raises TypeError and the turn dies.
    """
    args = remap_tool_arguments(execute_fn, arguments)
    try:
        signature = inspect.signature(execute_fn)
    except (TypeError, ValueError):
        return args
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return args
    accepted = {
        name
        for name, param in signature.parameters.items()
        if name != "self"
        and param.kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    }
    return {key: value for key, value in args.items() if key in accepted}


class BaseTool(ABC):
    """Abstract base class for all agent tools."""

    def __init__(self):
        self.name: str = ""
        self.description: str = ""
        self.parameters: dict[str, Any] = {}
        self.risk_level: str = "medium"  # "no"|"low"|"medium"|"high" — overridden by subclasses

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """Execute the tool with given parameters.

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            str: Result of the tool execution
        """
        pass

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert tool to OpenAI function calling schema.

        Returns:
            Dict containing the tool's schema in OpenAI format
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"
