"""Model discovery from OpenAI-compatible endpoints."""

from typing import List, Dict, Any, Optional
import aiohttp

from core.models.catalog import detect_preset_from_url
from core.models.client_factory import create_openai_client


class ModelDiscovery:
    """Discover models from OpenAI-compatible endpoints."""

    @staticmethod
    async def discover_models(
        base_url: str,
        api_key: str = "dummy",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Discover available models from an endpoint.

        Args:
            base_url: Base URL of the API endpoint
            api_key: API key for authentication

        Returns:
            List of model information dictionaries, each containing:
            - id: Model ID
            - created: Creation timestamp (if available)
            - owned_by: Owner (if available)
            - context_length: Context window in tokens (if available)
        """
        try:
            client = create_openai_client(
                base_url=base_url,
                api_key=api_key,
                metadata=metadata,
            )
            models = await client.models.list()

            model_list = []
            for model in models.data:
                model_info = {
                    "id": model.id,
                    "created": getattr(model, "created", None),
                    "owned_by": getattr(model, "owned_by", "unknown"),
                    "context_length": None,
                }
                model_list.append(model_info)

            # Try to get context lengths from Ollama API if detected
            provider_type = ModelDiscovery.detect_provider_type(base_url, metadata=metadata)
            if provider_type == "ollama":
                try:
                    context_map = await ModelDiscovery._get_ollama_context_lengths(base_url)
                    for model_info in model_list:
                        model_id = model_info["id"]
                        if model_id in context_map:
                            model_info["context_length"] = context_map[model_id]
                except Exception:
                    pass  # Non-critical — context_length will be None

            return model_list
        except Exception as e:
            raise Exception(f"Failed to discover models: {str(e)}")

    @staticmethod
    async def _get_ollama_context_lengths(base_url: str) -> Dict[str, int]:
        """Get context lengths for Ollama models via /api/show endpoint.

        Args:
            base_url: Base URL of the Ollama API (e.g., http://localhost:11434)

        Returns:
            Dict mapping model_id → context_length in tokens.
        """
        context_map = {}
        # Convert /v1 base URL to Ollama native API URL
        ollama_base = base_url.replace("/v1", "").rstrip("/")

        try:
            # First get list of running/local models
            async with aiohttp.ClientSession() as session:
                # Get list of local models
                async with session.get(f"{ollama_base}/api/tags", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = data.get("models", [])

                        for model in models:
                            model_id = model.get("name", "")
                            if not model_id:
                                continue

                            try:
                                # Query /api/show for model details
                                async with session.post(
                                    f"{ollama_base}/api/show",
                                    json={"name": model_id},
                                    timeout=aiohttp.ClientTimeout(total=10),
                                ) as show_resp:
                                    if show_resp.status == 200:
                                        show_data = await show_resp.json()
                                        # Try multiple paths where context_length may be
                                        context_length = None

                                        # Path 1: parameters.context_length
                                        params = show_data.get("parameters", {})
                                        if isinstance(params, dict):
                                            context_length = params.get("context_length") or params.get("num_ctx")

                                        # Path 2: model_info.context_length / model_info.token_limit
                                        model_info = show_data.get("model_info", {})
                                        if isinstance(model_info, dict) and not context_length:
                                            for key, value in model_info.items():
                                                if "context_length" in key or "token_limit" in key:
                                                    context_length = value
                                                    break

                                        if context_length and isinstance(context_length, (int, float)):
                                            context_map[model_id] = int(context_length)

                            except Exception:
                                continue  # Skip models we can't get info for

        except Exception:
            pass  # Non-critical

        return context_map

    @staticmethod
    async def test_endpoint(
        base_url: str,
        api_key: str = "dummy",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Test if endpoint is accessible and compatible.

        Args:
            base_url: Base URL of the API endpoint
            api_key: API key for authentication

        Returns:
            True if endpoint is accessible
        """
        try:
            client = create_openai_client(
                base_url=base_url,
                api_key=api_key,
                metadata=metadata,
            )
            await client.models.list()
            return True
        except Exception:
            return False

    @staticmethod
    async def get_model_info(
        base_url: str,
        model_id: str,
        api_key: str = "dummy",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific model.

        Args:
            base_url: Base URL of the API endpoint
            model_id: Model ID to query
            api_key: API key for authentication

        Returns:
            Model information dictionary or None
        """
        try:
            client = create_openai_client(
                base_url=base_url,
                api_key=api_key,
                metadata=metadata,
            )
            model = await client.models.retrieve(model_id)

            return {
                "id": model.id,
                "created": getattr(model, "created", None),
                "owned_by": getattr(model, "owned_by", "unknown"),
            }
        except Exception:
            return None

    @staticmethod
    def detect_provider_type(
        base_url: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Detect provider type from URL, metadata, or catalog."""
        if metadata and metadata.get("preset_id"):
            return str(metadata["preset_id"])
        preset = detect_preset_from_url(base_url)
        if preset:
            return preset
        base_url_lower = base_url.lower()
        if "localhost" in base_url_lower or "127.0.0.1" in base_url_lower:
            return "local"
        return "custom"
