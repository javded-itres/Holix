"""Holix-managed OpenCode config for profile model endpoints."""

from __future__ import annotations

import json
from pathlib import Path

from core.external_cli.grok_config import grok_model_registry_name
from core.models.manager import ModelConfig
from core.profile.names import profile_dir_for_name

HOLIX_OPENCODE_PROVIDER = "holix"


def opencode_launch_model(model: ModelConfig) -> str:
    """Return OpenCode ``provider/model`` id for ``-m`` and config default."""
    model_key = grok_model_registry_name(model.model)
    return f"{HOLIX_OPENCODE_PROVIDER}/{model_key}"


def ensure_opencode_config(
    profile: str,
    model: ModelConfig,
    *,
    api_key: str,
) -> tuple[Path, str]:
    """Write ``opencode.json`` for the profile and return ``(config_path, launch_model)``."""
    config_dir = (profile_dir_for_name(profile) / "opencode").resolve()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "opencode.json"

    model_key = grok_model_registry_name(model.model)
    launch_model = f"{HOLIX_OPENCODE_PROVIDER}/{model_key}"
    base_url = (model.base_url or "").rstrip("/")
    display_name = (model.model or "").strip() or model_key

    provider: dict[str, object] = {
        "npm": "@ai-sdk/openai-compatible",
        "name": "Holix",
        "options": {
            "apiKey": api_key,
        },
        "models": {
            model_key: {
                "name": f"Holix {display_name}",
                "tool_call": True,
            },
        },
    }
    if base_url:
        provider["options"]["baseURL"] = base_url

    config = {
        "$schema": "https://opencode.ai/config.json",
        "model": launch_model,
        "provider": {
            HOLIX_OPENCODE_PROVIDER: provider,
        },
    }
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return config_path, launch_model