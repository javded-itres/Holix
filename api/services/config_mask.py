"""Mask secrets in profile/global config payloads."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from api.services.env_mask import _is_sensitive


def _mask_value(key: str, value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return value
    if _is_sensitive(key) or key == "api_key":
        return "***" if len(value) <= 8 else f"{value[:3]}…{value[-2:]}"
    return value


def mask_config_dict(data: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(data)
    for key, value in out.items():
        if key == "providers" and isinstance(value, dict):
            for provider_name, provider_data in value.items():
                if isinstance(provider_data, dict) and "api_key" in provider_data:
                    provider_data["api_key"] = _mask_value("api_key", provider_data["api_key"])
        elif key == "mcp_servers" and isinstance(value, dict):
            for server_data in value.values():
                if isinstance(server_data, dict) and isinstance(server_data.get("env"), dict):
                    server_data["env"] = {
                        env_key: _mask_value(env_key, env_val)
                        for env_key, env_val in server_data["env"].items()
                    }
        elif isinstance(value, str):
            out[key] = _mask_value(key, value)
    return out