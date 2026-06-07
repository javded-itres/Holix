"""Model manager for handling providers and routing."""

from typing import Optional, Dict, Any
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from core.models.client_factory import create_openai_client


class ModelConfig(BaseModel):
    """Configuration for a specific model usage."""

    provider: str
    model: str
    base_url: str
    api_key: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    context_window: Optional[int] = None  # Context window in tokens, None = use default
    metadata: Dict[str, Any] = Field(default_factory=dict)


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

        providers = self.profile_config.providers or {}
        default_provider = self.profile_config.default_provider

        if providers:
            if not default_provider or default_provider not in providers:
                return None
            provider_data = providers[default_provider]
            if not provider_data:
                return None
            model_id = provider_data.get("default_model", "") or ""
            model_contexts = provider_data.get("model_contexts", {})
            context_window = model_contexts.get(model_id) if model_contexts else None
            if hasattr(self.profile_config, "context_window") and self.profile_config.context_window:
                context_window = self.profile_config.context_window
            base_url = (provider_data.get("base_url") or "").strip()
            if not base_url:
                return None
            return ModelConfig(
                provider=default_provider,
                model=model_id,
                base_url=base_url,
                api_key=provider_data.get("api_key", "dummy"),
                temperature=self.profile_config.temperature,
                context_window=context_window,
                metadata=dict(provider_data.get("metadata") or {}),
            )

        # Stale default_provider with empty providers — do not fall back to legacy defaults
        if default_provider:
            return None

        if getattr(self.profile_config, "models_via_providers", False):
            return None

        model = (self.profile_config.model or "").strip()
        base_url = (self.profile_config.base_url or "").strip()
        if not model or not base_url:
            return None

        context_window = None
        if hasattr(self.profile_config, "context_window") and self.profile_config.context_window:
            context_window = self.profile_config.context_window

        return ModelConfig(
            provider="legacy",
            model=model,
            base_url=base_url,
            api_key=self.profile_config.api_key or "dummy",
            temperature=self.profile_config.temperature,
            context_window=context_window,
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
        providers = self.profile_config.providers or {}
        provider_data = providers.get(provider_name) if provider_name else None

        if not provider_data:
            return None

        model_id = agent_data.get("model", "")
        # Get context_window: agent override → provider model_contexts → profile → None
        model_contexts = provider_data.get("model_contexts", {})
        context_window = agent_data.get("context_window")
        if not context_window:
            context_window = model_contexts.get(model_id) if model_contexts else None
        if not context_window and hasattr(self.profile_config, 'context_window') and self.profile_config.context_window:
            context_window = self.profile_config.context_window

        return ModelConfig(
            provider=provider_name,
            model=model_id,
            base_url=provider_data.get("base_url", ""),
            api_key=provider_data.get("api_key", "dummy"),
            temperature=agent_data.get("temperature", 0.7),
            max_tokens=agent_data.get("max_tokens"),
            context_window=context_window,
            metadata=dict(provider_data.get("metadata") or {}),
        )

    def get_client(self, model_config: ModelConfig) -> AsyncOpenAI:
        """Get or create OpenAI client for model config.

        Args:
            model_config: Model configuration

        Returns:
            AsyncOpenAI client
        """
        cache_key = f"{model_config.base_url}|{model_config.provider}"

        if cache_key not in self._clients:
            self._clients[cache_key] = create_openai_client(
                base_url=model_config.base_url,
                api_key=model_config.api_key,
                metadata=model_config.metadata,
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
