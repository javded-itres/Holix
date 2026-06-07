"""Create OpenAI-compatible clients with provider-specific auth headers."""

from __future__ import annotations

import os
from typing import Any

from openai import AsyncOpenAI

from core.config_utils import resolve_env_refs


def resolve_provider_api_key(api_key: str, *, preset_id: str | None = None) -> str:
    """Resolve ${ENV:VAR} placeholders and apply preset defaults."""
    resolved = resolve_env_refs(api_key)
    if isinstance(resolved, str) and resolved.strip():
        return resolved.strip()
    if preset_id in ("ollama", "vllm") or api_key in ("", "dummy", "ollama", "EMPTY"):
        return "EMPTY" if preset_id == "vllm" or api_key == "EMPTY" else "ollama"
    return resolved if isinstance(resolved, str) else "dummy"


def build_default_headers(metadata: dict[str, Any] | None) -> dict[str, str]:
    """Extra HTTP headers for providers (e.g. OpenRouter)."""
    if not metadata:
        return {}

    auth_type = (metadata.get("auth_type") or "bearer").lower()
    headers: dict[str, str] = {}

    if auth_type == "openrouter":
        referer = metadata.get("http_referer") or os.environ.get("OPENROUTER_HTTP_REFERER", "")
        title = metadata.get("x_title") or os.environ.get("OPENROUTER_APP_TITLE", "Helix")
        referer = resolve_env_refs(referer) if isinstance(referer, str) else referer
        title = resolve_env_refs(title) if isinstance(title, str) else title
        if referer:
            headers["HTTP-Referer"] = str(referer)
        if title:
            headers["X-Title"] = str(title)

    for key, value in metadata.get("default_headers", {}).items():
        if value is not None:
            resolved = resolve_env_refs(value) if isinstance(value, str) else value
            headers[str(key)] = str(resolved)

    return headers


def create_openai_client(
    *,
    base_url: str,
    api_key: str,
    metadata: dict[str, Any] | None = None,
) -> AsyncOpenAI:
    """Build AsyncOpenAI client with resolved key and provider headers."""
    preset_id = (metadata or {}).get("preset_id")
    resolved_key = resolve_provider_api_key(api_key, preset_id=preset_id)
    headers = build_default_headers(metadata)

    kwargs: dict[str, Any] = {
        "base_url": base_url,
        "api_key": resolved_key,
    }
    if headers:
        kwargs["default_headers"] = headers

    return AsyncOpenAI(**kwargs)