"""Profile cleanup when providers or model routing change."""

from __future__ import annotations

from typing import Any


def remove_provider_from_profile(config: Any, name: str) -> list[str]:
    """Remove a provider and fix dependent profile fields.

    Returns human-readable notes about what was changed.
    """
    providers = config.providers or {}
    if name not in providers:
        return [f"Provider '{name}' not found"]

    del providers[name]
    config.providers = providers
    notes: list[str] = [f"Removed provider '{name}'"]

    removed_agents = _prune_agent_models_for_provider(config, name)
    if removed_agents:
        notes.append(f"Removed agent_models: {', '.join(removed_agents)}")

    if config.default_provider == name:
        if providers:
            config.default_provider = next(iter(providers))
            notes.append(f"default_provider → '{config.default_provider}'")
        else:
            config.default_provider = None
            _clear_legacy_llm_fields(config)
            notes.append("Cleared legacy model/base_url (no providers left)")

    if getattr(config, "models_via_providers", False) and not providers:
        _clear_legacy_llm_fields(config)
        config.models_via_providers = False

    return notes


def _prune_agent_models_for_provider(config: Any, provider_name: str) -> list[str]:
    agent_models = getattr(config, "agent_models", None) or {}
    if not agent_models:
        return []

    removed: list[str] = []
    for agent_name, raw in list(agent_models.items()):
        prov = raw.get("provider") if isinstance(raw, dict) else None
        if prov == provider_name:
            del agent_models[agent_name]
            removed.append(agent_name)
    config.agent_models = agent_models
    return removed


def _clear_legacy_llm_fields(config: Any) -> None:
    config.model = ""
    config.base_url = ""
    config.api_key = ""


def profile_has_llm_config(config: Any) -> bool:
    """True if profile has a resolvable default LLM configuration."""
    from core.models.manager import ModelManager

    mc = ModelManager(config).get_default_model_config()
    return bool(mc and (mc.base_url or "").strip() and (mc.model or "").strip())


MISSING_LLM_HINT = (
    "No LLM configured. Run: [bold]helix models setup[/bold] "
    "or [bold]helix models add <preset>[/bold]"
)


def sanitize_model_routing_data(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize profile YAML data after provider removal (in-memory only)."""
    out = dict(data)
    providers = dict(out.get("providers") or {})
    out["providers"] = providers

    default_provider = out.get("default_provider")
    original_agent_models = dict(out.get("agent_models") or {})

    agent_models = dict(original_agent_models)
    for name, raw in list(agent_models.items()):
        if not isinstance(raw, dict):
            continue
        prov = raw.get("provider")
        if prov and prov not in providers:
            del agent_models[name]
    out["agent_models"] = agent_models

    if default_provider and default_provider not in providers:
        out["default_provider"] = None
        default_provider = None

    if providers:
        out["models_via_providers"] = True
        return out

    had_provider_routing = bool(
        out.get("models_via_providers")
        or default_provider
        or any(
            isinstance(v, dict) and v.get("provider")
            for v in original_agent_models.values()
        )
    )
    if had_provider_routing:
        out["models_via_providers"] = True
        out["default_provider"] = None
        if out.get("model") or out.get("base_url"):
            out["model"] = ""
            out["base_url"] = ""
            out["api_key"] = ""

    return out