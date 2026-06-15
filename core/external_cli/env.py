"""Map Holix profile models to external CLI environment variables."""

from __future__ import annotations

import os
import re
from typing import Any

from core.external_cli.grok_config import ensure_grok_config, grok_model_registry_name
from core.external_cli.opencode_config import ensure_opencode_config, opencode_launch_model
from core.external_cli.registry import ExternalCliSpec
from core.models.manager import ModelConfig, ModelManager

_ENV_VAR_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")

_ANTHROPIC_MODEL_ALIASES = frozenset({
    "default",
    "best",
    "fable",
    "sonnet",
    "opus",
    "haiku",
    "opusplan",
})


def _resolve_api_key(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    match = _ENV_VAR_RE.fullmatch(value)
    if match:
        return os.environ.get(match.group(1), "")
    return value


def _normalize_anthropic_base_url(base_url: str) -> str:
    """Claude Code appends ``/v1/messages``; Holix providers store ``…/v1``."""
    url = base_url.rstrip("/")
    if url.endswith("/v1"):
        return url[:-3]
    return url


def _is_anthropic_gateway(base_url: str) -> bool:
    return "api.anthropic.com" not in base_url.lower()


def _is_known_anthropic_model(model_name: str) -> bool:
    """Return True when Claude Code accepts the model without custom gateway config."""
    name = (model_name or "").strip().lower()
    if not name:
        return False
    base = name.split("[", 1)[0]
    if base in _ANTHROPIC_MODEL_ALIASES:
        return True
    return base.startswith("claude") or base.startswith("anthropic.")


def _apply_anthropic_gateway_env(env: dict[str, str], base_url: str, model_name: str) -> None:
    if not base_url or not _is_anthropic_gateway(base_url):
        return
    env["CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY"] = "1"
    if model_name and not _is_known_anthropic_model(model_name):
        env["ANTHROPIC_CUSTOM_MODEL_OPTION"] = model_name
        env["ANTHROPIC_CUSTOM_MODEL_OPTION_NAME"] = model_name


def resolve_model_for_slot(profile_config: Any, model_slot: str) -> ModelConfig | None:
    manager = ModelManager(profile_config)
    slot = (model_slot or "main").strip() or "main"
    if slot == "main":
        return manager.get_default_model_config()
    return manager.get_agent_model_config(slot)


def _launch_model_name(spec: ExternalCliSpec, model: ModelConfig) -> str:
    if spec.env_style == "grok":
        return grok_model_registry_name(model.model)
    if spec.env_style == "opencode":
        return opencode_launch_model(model)
    return (model.model or "").strip()


def build_cli_env(
    spec: ExternalCliSpec,
    model: ModelConfig,
    *,
    profile: str | None = None,
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
            gateway_base_url = _normalize_anthropic_base_url(base_url)
            env["ANTHROPIC_BASE_URL"] = gateway_base_url
            env["ANTHROPIC_AUTH_TOKEN"] = api_key
            _apply_anthropic_gateway_env(env, gateway_base_url, model_name)
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
    elif spec.env_style == "grok":
        grok_home, _registry = ensure_grok_config(profile or "default", model)
        env["GROK_HOME"] = str(grok_home)
        env["XAI_API_KEY"] = api_key
        if base_url:
            env["GROK_MODELS_BASE_URL"] = base_url
    elif spec.env_style == "opencode":
        config_path, _launch_model = ensure_opencode_config(
            profile or "default",
            model,
            api_key=api_key,
        )
        env["OPENCODE_CONFIG"] = str(config_path)
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


def build_launch_args(
    spec: ExternalCliSpec,
    model: ModelConfig,
    task: str = "",
) -> tuple[str, ...]:
    """Build CLI argv tail (static launch_args + model flag + optional task)."""
    args = list(spec.launch_args)
    model_name = _launch_model_name(spec, model)
    if spec.model_cli_flag and model_name:
        args.extend([spec.model_cli_flag, model_name])
    task_text = (task or "").strip()
    if task_text:
        if spec.task_cli_flag:
            args.extend([spec.task_cli_flag, task_text])
        elif spec.task_positional:
            args.append(task_text)
    return tuple(args)


def task_passed_in_launch_args(spec: ExternalCliSpec, task: str) -> bool:
    task_text = (task or "").strip()
    return bool(task_text and (spec.task_cli_flag or spec.task_positional))


def env_export_shell(env: dict[str, str]) -> str:
    """Serialize env dict as shell export statements (safe for bash -c)."""
    parts: list[str] = []
    for key, value in sorted(env.items()):
        escaped = value.replace("'", "'\"'\"'")
        parts.append(f"export {key}='{escaped}'")
    return "; ".join(parts)