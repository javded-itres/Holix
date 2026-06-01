"""Model provider configuration and management."""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from openai import AsyncOpenAI


class ProviderConfig(BaseModel):
    """Configuration for a model provider."""

    name: str = Field(..., description="Provider name (e.g., 'ollama', 'litellm', 'openai')")
    base_url: str = Field(..., description="Base URL for the provider API")
    api_key: str = Field(default="dummy", description="API key for authentication")
    default_model: Optional[str] = Field(default=None, description="Default model to use")
    available_models: List[str] = Field(default_factory=list, description="List of available models")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional provider metadata")


class ModelProvider:
    """Manage model providers and their configurations."""

    def __init__(self, config: ProviderConfig):
        """Initialize model provider.

        Args:
            config: Provider configuration
        """
        self.config = config
        self._client: Optional[AsyncOpenAI] = None

    @property
    def client(self) -> AsyncOpenAI:
        """Get or create OpenAI client for this provider.

        Returns:
            AsyncOpenAI client instance
        """
        if self._client is None:
            self._client = AsyncOpenAI(
                base_url=self.config.base_url,
                api_key=self.config.api_key,
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

    async def get_available_models(self) -> List[str]:
        """Get list of available models from provider.

        Returns:
            List of model names
        """
        try:
            models = await self.client.models.list()
            return [model.id for model in models.data]
        except Exception:
            return []

    def to_dict(self) -> Dict[str, Any]:
        """Convert provider config to dictionary.

        Returns:
            Dictionary representation
        """
        return self.config.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelProvider":
        """Create provider from dictionary.

        Args:
            data: Dictionary data

        Returns:
            ModelProvider instance
        """
        config = ProviderConfig(**data)
        return cls(config)
