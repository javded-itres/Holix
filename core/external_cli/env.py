"""Map Holix profile models to external CLI environment variables."""

from __future__ import annotations

import os
import re
from typing import Any

from core.external_cli.registry import ExternalCliSpec
from core.models.manager import ModelConfig, ModelManager

_ENV_VAR_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _resolve_api_key(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    match = _ENV_VAR_RE.fullmatch(value)
    if match:
        return os.environ.get(match.group(1), "")
    return value


def resolve_model_for_slot(profile_config: Any, model_slot: str) -> ModelConfig | None:
    manager = ModelManager(profile_config)
    slot = (model_slot or "main").strip() or "main"
    if slot == "main":
        return manager.get_default_model_config()
    return manager.get_agent_model_config(slot)


def build_cli_env(
    spec: ExternalCliSpec,
    model: ModelConfig,
    *,
    extra_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build environment variables for an external CLI from a Holix ModelConfig."""
    api_key = _resolve_api_key(model.api_key)
    base_url = (model.base_url or "").rstrip("/")
    model_name = (model.model or "").strip()
    env: dict[str, str] = {}

    if spec.env_style == "anthropic":
        env["ANTHROPIC_API_KEY"] = api_key
        if base_url:
            env["ANTHROPIC_BASE_URL"] = base_url
            env["ANTHROPIC_AUTH_TOKEN"] = api_key
        if model_name:
            env["ANTHROPIC_MODEL"] = model_name
            env["CLAUDE_CODE_SUBAGENT_MODEL"] = model_name
    elif spec.env_style == "gigacode":
        env["GIGACODE_API_KEY"] = api_key
        if base_url:
            env["GIGACODE_BASE_URL"] = base_url
        if model_name:
            env["GIGACODE_MODEL"] = model_name
        env["OPENAI_API_KEY"] = api_key
        if base_url:
            env["OPENAI_BASE_URL"] = base_url
        if model_name:
            env["OPENAI_MODEL"] = model_name
    else:
        env["OPENAI_API_KEY"] = api_key
        if base_url:
            env["OPENAI_BASE_URL"] = base_url
        if model_name:
            env["OPENAI_MODEL"] = model_name
            env["LLM_MODEL"] = model_name

    env["HOLIX_LAUNCH_CLI"] = spec.cli_id
    env["HOLIX_LAUNCH_MODEL"] = model_name
    env["HOLIX_LAUNCH_PROVIDER"] = model.provider
    if extra_env:
        env.update({k: v for k, v in extra_env.items() if v is not None})
    return {k: v for k, v in env.items() if v}


def env_export_shell(env: dict[str, str]) -> str:
    """Serialize env dict as shell export statements (safe for bash -c)."""
    parts: list[str] = []
    for key, value in sorted(env.items()):
        escaped = value.replace("'", "'\"'\"'")
        parts.append(f"export {key}='{escaped}'")
    return "; ".join(parts)