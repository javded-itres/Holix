"""Model selection and routing for agents and sub-agents."""

from typing import Any

from pydantic import BaseModel, Field


class AgentModelConfig(BaseModel):
    """Model configuration for an agent or sub-agent."""

    agent_name: str = Field(..., description="Agent or sub-agent name")
    provider: str = Field(..., description="Provider name")
    model: str = Field(..., description="Model ID to use")
    temperature: float = Field(default=0.7, description="Temperature for generation")
    max_tokens: int | None = Field(default=None, description="Maximum tokens to generate")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ModelSelector:
    """Select and route models for different agents and sub-agents."""

    def __init__(self):
        """Initialize model selector."""
        self.agent_models: dict[str, AgentModelConfig] = {}
        self.default_config: AgentModelConfig | None = None

    def set_default_model(self, config: AgentModelConfig):
        """Set default model configuration.

        Args:
            config: Default model configuration
        """
        self.default_config = config

    def set_agent_model(self, agent_name: str, config: AgentModelConfig):
        """Set model configuration for a specific agent.

        Args:
            agent_name: Agent or sub-agent name
            config: Model configuration
        """
        config.agent_name = agent_name
        self.agent_models[agent_name] = config

    def get_agent_model(self, agent_name: str) -> AgentModelConfig | None:
        """Get model configuration for an agent.

        Args:
            agent_name: Agent or sub-agent name

        Returns:
            Model configuration or None
        """
        return self.agent_models.get(agent_name, self.default_config)

    def remove_agent_model(self, agent_name: str) -> bool:
        """Remove model configuration for an agent.

        Args:
            agent_name: Agent or sub-agent name

        Returns:
            True if removed
        """
        if agent_name in self.agent_models:
            del self.agent_models[agent_name]
            return True
        return False

    def list_agent_models(self) -> list[AgentModelConfig]:
        """List all configured agent models.

        Returns:
            List of agent model configurations
        """
        return list(self.agent_models.values())

    def to_dict(self) -> dict[str, Any]:
        """Convert selector state to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "default_config": self.default_config.model_dump() if self.default_config else None,
            "agent_models": {name: config.model_dump() for name, config in self.agent_models.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelSelector":
        """Create selector from dictionary.

        Args:
            data: Dictionary data

        Returns:
            ModelSelector instance
        """
        selector = cls()

        if data.get("default_config"):
            selector.default_config = AgentModelConfig(**data["default_config"])

        for name, config_data in data.get("agent_models", {}).items():
            selector.agent_models[name] = AgentModelConfig(**config_data)

        return selector
