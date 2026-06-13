"""Seed Telegram user profiles with LLM settings from the bot profile."""

from __future__ import annotations

from typing import Any

from cli.core import ProfileManager

# Shared runtime settings copied from the Telegram bot profile to each user profile.
_TELEGRAM_USER_SHARED_CONFIG_KEYS: frozenset[str] = frozenset({
    "model",
    "base_url",
    "api_key",
    "temperature",
    "max_steps",
    "default_provider",
    "providers",
    "agent_models",
    "fallback_providers",
    "models_via_providers",
    "context_window",
    "mcp_servers",
    "mcp_assignments",
    "mcp_enabled",
    "skill_assignments",
    "search",
})


def _is_placeholder_model_config(config: Any) -> bool:
    from core.models.manager import ModelConfig, ModelManager

    mc = ModelManager(config).get_default_model_config()
    if mc is None:
        return True
    if not isinstance(mc, ModelConfig):
        return True
    return (
        mc.provider == "legacy"
        and mc.model == "qwen2.5-coder:32b"
        and mc.base_url == "http://localhost:11434/v1"
        and mc.api_key in ("ollama", "dummy", "")
    )


def _bot_has_meaningful_llm_config(manager: ProfileManager, bot_profile: str) -> bool:
    from core.models.manager import ModelManager

    bot_cfg = manager.load_profile(bot_profile)
    if bot_cfg.providers and bot_cfg.default_provider:
        return ModelManager(bot_cfg).get_default_model_config() is not None
    return not _is_placeholder_model_config(bot_cfg)


def _collect_bot_shared_overrides(
    manager: ProfileManager,
    bot_profile: str,
) -> dict[str, Any]:
    from core.global_config import extract_profile_overrides, load_global_config_resolved

    bot_cfg = manager.load_profile(bot_profile)
    global_data = load_global_config_resolved()
    overrides = extract_profile_overrides(bot_cfg.model_dump(), global_data)

    shared = {
        key: value
        for key, value in overrides.items()
        if key in _TELEGRAM_USER_SHARED_CONFIG_KEYS
        and value is not None
        and value is not False
        and value != ""
        and not (isinstance(value, (dict, list)) and not value)
    }
    if shared:
        return shared

    # Bot may store a full config while global is empty — copy resolved model settings.
    bot_data = bot_cfg.model_dump()
    for key in _TELEGRAM_USER_SHARED_CONFIG_KEYS:
        value = bot_data.get(key)
        if value is None or value is False or value == "":
            continue
        if isinstance(value, (dict, list)) and not value:
            continue
        global_val = global_data.get(key)
        if value != global_val:
            shared[key] = value
    return shared


def _seed_profile_env_from_bot(bot_profile: str, user_profile: str) -> None:
    from core.env_loader import holix_env_path, profile_env_path

    try:
        from core.crypto.profile_files import dotenv_values_for_path
        from dotenv import dotenv_values
    except ImportError:
        return

    bot_env = profile_env_path(bot_profile)
    if not bot_env.is_file():
        return

    bot_values = {
        key: value
        for key, value in dotenv_values_for_path(bot_env, profile=bot_profile).items()
        if value is not None and str(value).strip()
    }
    if not bot_values:
        return

    global_values: dict[str, str | None] = {}
    try:
        from core.global_config import global_env_path

        gpath = global_env_path()
        if gpath.is_file():
            global_values.update(dotenv_values(gpath))
    except Exception:
        pass
    legacy = holix_env_path()
    if legacy.is_file():
        global_values.update(dotenv_values(legacy))

    to_copy = {
        key: value
        for key, value in bot_values.items()
        if key not in global_values or global_values.get(key) != value
    }
    if not to_copy:
        return

    user_env = profile_env_path(user_profile)
    user_env.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if user_env.is_file():
        lines.append(user_env.read_text(encoding="utf-8").rstrip())
        lines.append("")
    else:
        lines.append(
            "# Inherited from Telegram bot profile — overrides global .env when set",
        )
    for key in sorted(to_copy):
        lines.append(f"{key}={to_copy[key]}")
    user_env.write_text("\n".join(lines) + "\n", encoding="utf-8")


def seed_telegram_user_profile_from_bot(
    manager: ProfileManager,
    *,
    bot_profile: str,
    user_profile: str,
) -> bool:
    """Copy LLM/runtime settings from the bot profile into a Telegram user profile."""
    bot_profile = (bot_profile or "default").strip() or "default"
    user_profile = (user_profile or "").strip()
    if not user_profile or bot_profile == user_profile:
        return False
    if not manager.profile_exists(bot_profile) or not manager.profile_exists(user_profile):
        return False

    if not _bot_has_meaningful_llm_config(manager, bot_profile):
        return False

    user_cfg = manager.load_profile(user_profile)
    if not _is_placeholder_model_config(user_cfg):
        _seed_profile_env_from_bot(bot_profile, user_profile)
        return False

    shared = _collect_bot_shared_overrides(manager, bot_profile)
    if not shared:
        return False

    for key, value in shared.items():
        setattr(user_cfg, key, value)
    manager.save_profile(user_profile, user_cfg, storage_mode="sparse")
    _seed_profile_env_from_bot(bot_profile, user_profile)
    return True