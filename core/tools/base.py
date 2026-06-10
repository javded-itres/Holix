from abc import ABC, abstractmethod
from typing import Any


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
                "parameters": self.parameters
            }
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"
