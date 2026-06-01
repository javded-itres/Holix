"""Model discovery from OpenAI-compatible endpoints."""

from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
import aiohttp


class ModelDiscovery:
    """Discover models from OpenAI-compatible endpoints."""

    @staticmethod
    async def discover_models(base_url: str, api_key: str = "dummy") -> List[Dict[str, Any]]:
        """Discover available models from an endpoint.

        Args:
            base_url: Base URL of the API endpoint
            api_key: API key for authentication

        Returns:
            List of model information dictionaries
        """
        try:
            client = AsyncOpenAI(base_url=base_url, api_key=api_key)
            models = await client.models.list()

            model_list = []
            for model in models.data:
                model_info = {
                    "id": model.id,
                    "created": getattr(model, "created", None),
                    "owned_by": getattr(model, "owned_by", "unknown"),
                }
                model_list.append(model_info)

            return model_list
        except Exception as e:
            raise Exception(f"Failed to discover models: {str(e)}")

    @staticmethod
    async def test_endpoint(base_url: str, api_key: str = "dummy") -> bool:
        """Test if endpoint is accessible and compatible.

        Args:
            base_url: Base URL of the API endpoint
            api_key: API key for authentication

        Returns:
            True if endpoint is accessible
        """
        try:
            client = AsyncOpenAI(base_url=base_url, api_key=api_key)
            await client.models.list()
            return True
        except Exception:
            return False

    @staticmethod
    async def get_model_info(base_url: str, model_id: str, api_key: str = "dummy") -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific model.

        Args:
            base_url: Base URL of the API endpoint
            model_id: Model ID to query
            api_key: API key for authentication

        Returns:
            Model information dictionary or None
        """
        try:
            client = AsyncOpenAI(base_url=base_url, api_key=api_key)
            model = await client.models.retrieve(model_id)

            return {
                "id": model.id,
                "created": getattr(model, "created", None),
                "owned_by": getattr(model, "owned_by", "unknown"),
            }
        except Exception:
            return None

    @staticmethod
    def detect_provider_type(base_url: str) -> str:
        """Detect provider type from base URL.

        Args:
            base_url: Base URL of the API endpoint

        Returns:
            Provider type string (ollama, litellm, openai, etc.)
        """
        base_url_lower = base_url.lower()

        if "ollama" in base_url_lower or "11434" in base_url_lower:
            return "ollama"
        elif "litellm" in base_url_lower or "4000" in base_url_lower:
            return "litellm"
        elif "openai" in base_url_lower or "api.openai.com" in base_url_lower:
            return "openai"
        elif "localhost" in base_url_lower or "127.0.0.1" in base_url_lower:
            return "local"
        else:
            return "custom"
