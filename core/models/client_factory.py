"""Create OpenAI-compatible clients with provider-specific auth headers."""

from __future__ import annotations

import os
from typing import Any

import httpx
from openai import AsyncOpenAI

from core.config_utils import resolve_env_refs

_LOCAL_PRESET_PLACEHOLDER_KEYS = {
    "ollama": "ollama",
    "vllm": "EMPTY",
}


def resolve_provider_api_key(api_key: str, *, preset_id: str | None = None) -> str:
    """Resolve ${ENV:VAR} placeholders and apply preset defaults."""
    resolved = resolve_env_refs(api_key)
    if isinstance(resolved, str):
        stripped = resolved.strip()
        if stripped and stripped not in ("dummy",):
            return stripped
    if preset_id in _LOCAL_PRESET_PLACEHOLDER_KEYS:
        return _LOCAL_PRESET_PLACEHOLDER_KEYS[preset_id]
    if api_key in ("ollama", "EMPTY"):
        return api_key
    return ""


def build_default_headers(metadata: dict[str, Any] | None) -> dict[str, str]:
    """Extra HTTP headers for providers (e.g. OpenRouter)."""
    if not metadata:
        return {}

    auth_type = (metadata.get("auth_type") or "bearer").lower()
    headers: dict[str, str] = {}

    if auth_type == "openrouter":
        referer = metadata.get("http_referer") or os.environ.get("OPENROUTER_HTTP_REFERER", "")
        title = metadata.get("x_title") or os.environ.get("OPENROUTER_APP_TITLE", "Holix")
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


def resolve_verify_ssl(metadata: dict[str, Any] | None) -> bool:
    """Whether to verify TLS certificates (default True)."""
    if not metadata:
        return True
    val = metadata.get("verify_ssl")
    if val is None:
        val = metadata.get("ssl_verify")
    if val is None:
        return True
    if isinstance(val, str):
        return val.strip().lower() not in {"0", "false", "no", "off"}
    return bool(val)


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

    if not resolve_verify_ssl(metadata):
        kwargs["http_client"] = httpx.AsyncClient(verify=False)

    return AsyncOpenAI(**kwargs)