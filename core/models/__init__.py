"""Model provider and management system."""

from .catalog import (
    ProviderPreset,
    build_base_url_from_host,
    get_provider_preset,
    list_provider_presets,
    parse_host_value,
    resolve_preset_base_url,
)
from .client_factory import create_openai_client, resolve_provider_api_key
from .discovery import ModelDiscovery
from .manager import ModelConfig, ModelManager
from .provider import ModelProvider, ProviderConfig
from .selector import ModelSelector

__all__ = [
    "ModelProvider",
    "ProviderConfig",
    "ModelDiscovery",
    "ModelSelector",
    "ModelManager",
    "ModelConfig",
    "ProviderPreset",
    "get_provider_preset",
    "list_provider_presets",
    "build_base_url_from_host",
    "parse_host_value",
    "resolve_preset_base_url",
    "create_openai_client",
    "resolve_provider_api_key",
]
