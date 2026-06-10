"""Model provider configuration and management."""

from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from core.models.client_factory import create_openai_client


class ProviderConfig(BaseModel):
    """Configuration for a model provider."""

    name: str = Field(..., description="Provider name (e.g., 'ollama', 'litellm', 'openai')")
    base_url: str = Field(..., description="Base URL for the provider API")
    api_key: str = Field(default="dummy", description="API key for authentication")
    default_model: str | None = Field(default=None, description="Default model to use")
    available_models: list[str] = Field(default_factory=list, description="List of available models")
    model_contexts: dict[str, int] = Field(default_factory=dict, description="Mapping model_id → context_window in tokens")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional provider metadata")


class ModelProvider:
    """Manage model providers and their configurations."""

    def __init__(self, config: ProviderConfig):
        """Initialize model provider.

        Args:
            config: Provider configuration
        """
        self.config = config
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        """Get or create OpenAI client for this provider.

        Returns:
            AsyncOpenAI client instance
        """
        if self._client is None:
            self._client = create_openai_client(
                base_url=self.config.base_url,
                api_key=self.config.api_key,
                metadata=self.config.metadata,
            )
        return self._client

    async def test_connection(self) -> bool:
        """Test connection to the provider.

        Returns:
            True if connection is successful
        """
        try:
            # Try to list models
            await self.client.models.list()
            return True
        except Exception:
            return False

    async def get_available_models(self) -> list[str]:
        """Get list of available models from provider.

        Returns:
            List of model names
        """
        try:
            models = await self.client.models.list()
            return [model.id for model in models.data]
        except Exception:
            return []

    def to_dict(self) -> dict[str, Any]:
        """Convert provider config to dictionary.

        Returns:
            Dictionary representation
        """
        return self.config.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelProvider":
        """Create provider from dictionary.

        Args:
            data: Dictionary data

        Returns:
            ModelProvider instance
        """
        config = ProviderConfig(**data)
        return cls(config)
