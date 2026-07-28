"""Model discovery from OpenAI-compatible endpoints."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from core.models.catalog import detect_preset_from_url
from core.models.client_factory import create_openai_client, resolve_verify_ssl

logger = logging.getLogger(__name__)

# Keys that may carry context-window size on various OpenAI-compatible APIs.
_CONTEXT_KEYS = (
    "context_length",
    "context_window",
    "max_input_tokens",
    "max_model_len",
    "max_tokens",
    "max_seq_len",
    "n_ctx",
    "num_ctx",
    "token_limit",
)


def _coerce_positive_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def extract_context_length(payload: Any) -> int | None:
    """Best-effort extract of context window tokens from a nested dict/object."""
    if payload is None:
        return None
    if isinstance(payload, (int, float)) and not isinstance(payload, bool):
        return _coerce_positive_int(payload)

    data: dict[str, Any] = {}
    if isinstance(payload, dict):
        data = payload
    else:
        # pydantic / OpenAI SDK model objects
        for attr in ("model_extra", "model_dump", "dict", "__dict__"):
            raw = getattr(payload, attr, None)
            if callable(raw):
                try:
                    raw = raw()
                except Exception:
                    raw = None
            if isinstance(raw, dict):
                data = raw
                break
        if not data:
            for key in _CONTEXT_KEYS:
                val = getattr(payload, key, None)
                n = _coerce_positive_int(val)
                if n:
                    return n

    for key in _CONTEXT_KEYS:
        if key in data:
            n = _coerce_positive_int(data.get(key))
            if n:
                return n

    # Nested model_info / parameters (LiteLLM, Ollama, vLLM)
    for nest_key in ("model_info", "parameters", "metadata", "litellm_params"):
        nested = data.get(nest_key)
        if isinstance(nested, dict):
            n = extract_context_length(nested)
            if n:
                return n
        # model_info sometimes has keys like "llama.context_length"
        if nest_key == "model_info" and isinstance(nested, dict):
            for k, v in nested.items():
                if any(s in str(k).lower() for s in ("context", "token_limit", "max_seq")):
                    n = _coerce_positive_int(v)
                    if n:
                        return n
    return None


class ModelDiscovery:
    """Discover models from OpenAI-compatible endpoints."""

    @staticmethod
    async def discover_models(
        base_url: str,
        api_key: str = "dummy",
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Discover available models from an endpoint.

        Returns list of dicts with ``id``, ``created``, ``owned_by``,
        ``context_length`` (tokens, when known).

        Context resolution order per model:
        1. Fields on ``/v1/models`` object (if provider sends them)
        2. LiteLLM ``GET /model/info`` (when authorized)
        3. Ollama ``/api/show`` (ollama endpoints)
        4. ``litellm.get_model_info`` catalog for known public model ids
        """
        try:
            client = create_openai_client(
                base_url=base_url,
                api_key=api_key,
                metadata=metadata,
            )
            models = await client.models.list()

            model_list: list[dict[str, Any]] = []
            for model in models.data:
                model_list.append(
                    {
                        "id": model.id,
                        "created": getattr(model, "created", None),
                        "owned_by": getattr(model, "owned_by", "unknown"),
                        "context_length": extract_context_length(model),
                    }
                )

            provider_type = ModelDiscovery.detect_provider_type(
                base_url, metadata=metadata
            )

            # LiteLLM proxy: /v1/models usually omits context; /model/info has it
            # (may require master key — non-fatal on 403).
            if provider_type in {"litellm", "openai-compatible", "vllm", "unknown"}:
                try:
                    litellm_map = await ModelDiscovery._get_litellm_context_lengths(
                        base_url,
                        api_key=api_key,
                        metadata=metadata,
                    )
                    for model_info in model_list:
                        mid = model_info["id"]
                        if not model_info.get("context_length") and mid in litellm_map:
                            model_info["context_length"] = litellm_map[mid]
                except Exception as exc:
                    logger.debug("LiteLLM model/info enrichment failed: %s", exc)

            if provider_type == "ollama":
                try:
                    context_map = await ModelDiscovery._get_ollama_context_lengths(
                        base_url,
                        metadata=metadata,
                    )
                    for model_info in model_list:
                        model_id = model_info["id"]
                        if not model_info.get("context_length") and model_id in context_map:
                            model_info["context_length"] = context_map[model_id]
                except Exception:
                    pass  # Non-critical — context_length will be None

            # Catalog fallback for standard public model ids (gpt-4o, claude-*, …)
            for model_info in model_list:
                if model_info.get("context_length"):
                    continue
                n = ModelDiscovery.lookup_catalog_context(model_info["id"])
                if n:
                    model_info["context_length"] = n

            return model_list
        except Exception as e:
            raise Exception(f"Failed to discover models: {str(e)}") from e

    @staticmethod
    def lookup_catalog_context(model_id: str) -> int | None:
        """Resolve context from Holix presets and optional litellm package catalog."""
        mid = (model_id or "").strip()
        if not mid:
            return None

        # 1) Holix built-in preset tables (no extra dependency)
        try:
            from core.models.catalog import list_provider_presets

            for preset in list_provider_presets():
                ctx_map = preset.model_contexts or {}
                if mid in ctx_map:
                    return int(ctx_map[mid])
                # match bare id against openai/gpt-4o style keys
                for key, val in ctx_map.items():
                    if key == mid or key.endswith(f"/{mid}") or mid.endswith(f"/{key}"):
                        n = _coerce_positive_int(val)
                        if n:
                            return n
        except Exception:
            pass

        candidates = [mid]
        if "/" not in mid:
            for prefix in (
                "openai/",
                "anthropic/",
                "openrouter/",
                "deepseek/",
                "groq/",
            ):
                candidates.append(f"{prefix}{mid}")
        # Heuristic for Anthropic-style ids without catalog entry
        lower = mid.lower()
        if "claude" in lower and "opus" in lower:
            return 200_000
        if "claude" in lower and ("sonnet" in lower or "haiku" in lower):
            return 200_000
        if lower.startswith("gpt-4o") or lower.startswith("gpt-4.1"):
            return 128_000
        if "gemini" in lower and "flash" in lower:
            return 1_000_000
        if "llama-3.3" in lower or "llama3.3" in lower:
            return 128_000

        # 2) Optional litellm Python package (richer catalog when installed)
        try:
            import litellm  # type: ignore[import-untyped]

            for name in candidates:
                try:
                    info = litellm.get_model_info(name)
                except Exception:
                    continue
                n = extract_context_length(info if isinstance(info, dict) else {})
                if n:
                    return n
                if isinstance(info, dict):
                    n = _coerce_positive_int(
                        info.get("max_input_tokens") or info.get("max_tokens")
                    )
                    if n:
                        return n
        except Exception:
            pass
        return None
    @staticmethod
    async def _get_litellm_context_lengths(
        base_url: str,
        *,
        api_key: str = "dummy",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        """Fetch context windows from LiteLLM proxy ``GET /model/info``.

        Returns empty dict when the endpoint is missing or forbidden (user keys
        often cannot call admin model/info).
        """
        root = (base_url or "").rstrip("/")
        if root.endswith("/v1"):
            root = root[: -len("/v1")]
        url = f"{root}/model/info"
        verify_ssl = resolve_verify_ssl(metadata)
        connector = aiohttp.TCPConnector(ssl=verify_ssl)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "x-litellm-api-key": api_key,
        }
        out: dict[str, int] = {}
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=12),
                ) as resp:
                    if resp.status != 200:
                        logger.debug(
                            "LiteLLM /model/info status=%s (context not available)",
                            resp.status,
                        )
                        return out
                    payload = await resp.json()
        except Exception as exc:
            logger.debug("LiteLLM /model/info request failed: %s", exc)
            return out

        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            rows = payload if isinstance(payload, list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            # LiteLLM shapes vary: model_name, id, model_info.*
            mid = row.get("model_name") or row.get("id")
            info = row.get("model_info")
            if not mid and isinstance(info, dict):
                mid = info.get("id") or info.get("key") or info.get("model_name")
            mid = str(mid or "").strip()
            if not mid:
                continue
            ctx = extract_context_length(row)
            if not ctx and isinstance(info, dict):
                ctx = extract_context_length(info)
            if ctx:
                out[mid] = ctx
        return out
    @staticmethod
    async def _get_ollama_context_lengths(
        base_url: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        """Get context lengths for Ollama models via /api/show endpoint.

        Args:
            base_url: Base URL of the Ollama API (e.g., http://localhost:11434)

        Returns:
            Dict mapping model_id → context_length in tokens.
        """
        context_map = {}
        # Convert /v1 base URL to Ollama native API URL
        ollama_base = base_url.replace("/v1", "").rstrip("/")

        verify_ssl = resolve_verify_ssl(metadata)
        connector = aiohttp.TCPConnector(ssl=verify_ssl)

        try:
            # First get list of running/local models
            async with aiohttp.ClientSession(connector=connector) as session:
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
        metadata: dict[str, Any] | None = None,
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
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
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

            ctx = extract_context_length(model)
            if not ctx:
                ctx = ModelDiscovery.lookup_catalog_context(model_id)
            return {
                "id": model.id,
                "created": getattr(model, "created", None),
                "owned_by": getattr(model, "owned_by", "unknown"),
                "context_length": ctx,
            }
        except Exception:
            return None

    @staticmethod
    def detect_provider_type(
        base_url: str,
        metadata: dict[str, Any] | None = None,
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
