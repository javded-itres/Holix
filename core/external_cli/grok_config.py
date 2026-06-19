"""Holix-managed Grok Build config for custom model endpoints."""

from __future__ import annotations

import re
from pathlib import Path

from core.models.manager import ModelConfig
from core.profile.names import profile_dir_for_name


def grok_model_registry_name(raw: str) -> str:
    """Sanitize a Holix model id for Grok ``[model.<name>]`` and ``-m``."""
    name = re.sub(r"[^a-zA-Z0-9._-]", "-", (raw or "").strip()).strip("-")
    return name or "holix-model"


def _toml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def ensure_grok_config(profile: str, model: ModelConfig) -> tuple[Path, str]:
    """Write ``config.toml`` under the profile and return ``(grok_home, registry_name)``."""
    grok_home = (profile_dir_for_name(profile) / "grok").resolve()
    grok_home.mkdir(parents=True, exist_ok=True)

    registry_name = grok_model_registry_name(model.model)
    base_url = (model.base_url or "").rstrip("/")
    model_id = (model.model or "").strip() or registry_name
    display = f"Holix {registry_name}"

    lines = [
        "[models]",
        f'default = "{_toml_string(registry_name)}"',
        "",
        f"[model.{registry_name}]",
        f'model = "{_toml_string(model_id)}"',
    ]
    if base_url:
        lines.append(f'base_url = "{_toml_string(base_url)}"')
    lines.extend([
        f'name = "{_toml_string(display)}"',
        'env_key = "XAI_API_KEY"',
        'api_backend = "chat_completions"',
        "",
    ])
    (grok_home / "config.toml").write_text("\n".join(lines), encoding="utf-8")

    user_auth = Path.home() / ".grok" / "auth.json"
    holix_auth = grok_home / "auth.json"
    if user_auth.is_file() and not holix_auth.exists():
        try:
            holix_auth.symlink_to(user_auth)
        except OSError:
            pass

    return grok_home, registry_name