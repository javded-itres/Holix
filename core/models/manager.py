"""Model manager for handling providers and routing."""

from typing import Optional, Dict, Any
from openai import AsyncOpenAI
from pydantic import BaseModel


class ModelConfig(BaseModel):
    """Configuration for a specific model usage."""

    provider: str
    model: str
    base_url: str
    api_key: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None


class ModelManager:
    """Manage model providers and create clients."""

    def __init__(self, profile_config: Optional[Any] = None):
        """Initialize model manager.

        Args:
            profile_config: ProfileConfig instance with providers
        """
        self.profile_config = profile_config
        self._clients: Dict[str, AsyncOpenAI] = {}

    def get_default_model_config(self) -> Optional[ModelConfig]:
        """Get default model configuration from profile.

        Returns:
            ModelConfig or None
        """
        if not self.profile_config:
            return None

        # Try to get from default_provider
        if self.profile_config.default_provider and self.profile_config.providers:
            provider_name = self.profile_config.default_provider
            provider_data = self.profile_config.providers.get(provider_name)

            if provider_data:
                return ModelConfig(
                    provider=provider_name,
                    model=provider_data.get("default_model", ""),
                    base_url=provider_data.get("base_url", ""),
                    api_key=provider_data.get("api_key", "dummy"),
                    temperature=self.profile_config.temperature,
                )

        # Fallback to legacy config
        return ModelConfig(
            provider="legacy",
            model=self.profile_config.model,
            base_url=self.profile_config.base_url,
            api_key=self.profile_config.api_key,
            temperature=self.profile_config.temperature,
        )

    def get_agent_model_config(self, agent_name: str) -> Optional[ModelConfig]:
        """Get model configuration for specific agent.

        Args:
            agent_name: Agent or sub-agent name

        Returns:
            ModelConfig or None
        """
        if not self.profile_config or not self.profile_config.agent_models:
            return self.get_default_model_config()

        agent_data = self.profile_config.agent_models.get(agent_name)
        if not agent_data:
            return self.get_default_model_config()

        provider_name = agent_data.get("provider")
        provider_data = self.profile_config.providers.get(provider_name)

        if not provider_data:
            return self.get_default_model_config()

        return ModelConfig(
            provider=provider_name,
            model=agent_data.get("model", ""),
            base_url=provider_data.get("base_url", ""),
            api_key=provider_data.get("api_key", "dummy"),
            temperature=agent_data.get("temperature", 0.7),
            max_tokens=agent_data.get("max_tokens"),
        )

    def get_client(self, model_config: ModelConfig) -> AsyncOpenAI:
        """Get or create OpenAI client for model config.

        Args:
            model_config: Model configuration

        Returns:
            AsyncOpenAI client
        """
        # Use base_url as cache key
        cache_key = model_config.base_url

        if cache_key not in self._clients:
            self._clients[cache_key] = AsyncOpenAI(
                base_url=model_config.base_url,
                api_key=model_config.api_key,
            )

        return self._clients[cache_key]

    def get_default_client_and_model(self) -> tuple[AsyncOpenAI, str]:
        """Get default client and model name.

        Returns:
            Tuple of (client, model_name)
        """
        config = self.get_default_model_config()
        if not config:
            raise ValueError("No model configuration available")

        client = self.get_client(config)
        return client, config.model

    def get_agent_client_and_model(self, agent_name: str) -> tuple[AsyncOpenAI, str]:
        """Get client and model for specific agent.

        Args:
            agent_name: Agent or sub-agent name

        Returns:
            Tuple of (client, model_name)
        """
        config = self.get_agent_model_config(agent_name)
        if not config:
            return self.get_default_client_and_model()

        client = self.get_client(config)
        return client, config.model
