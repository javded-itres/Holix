"""Refresh a connected provider's model list and set its default model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.models.client_factory import resolve_provider_api_key
from core.models.setup_helpers import apply_live_model_ids, probe_provider


@dataclass(frozen=True, slots=True)
class RefreshStats:
    """Result of replacing a provider's cached model list."""

    provider: str
    models: list[str]
    default_model: str
    added: list[str]
    removed: list[str]


def _provider_map(config: Any) -> dict[str, Any]:
    return dict(getattr(config, "providers", None) or {})


def _require_provider(config: Any, provider_name: str) -> dict[str, Any]:
    name = (provider_name or "").strip()
    providers = _provider_map(config)
    if not name or name not in providers:
        known = ", ".join(sorted(providers)) or "(none)"
        raise ValueError(f"Unknown provider '{provider_name}'. Configured: {known}")
    pdata = providers[name]
    if not isinstance(pdata, dict):
        raise ValueError(f"Provider '{name}' has no configuration")
    return dict(pdata)


async def discover_provider_models(
    provider_name: str, provider_data: dict[str, Any]
) -> list[dict[str, Any]]:
    """Probe ``/v1/models`` for an already configured provider."""
    base_url = str(provider_data.get("base_url") or "").strip()
    if not base_url:
        raise RuntimeError(f"Provider '{provider_name}' has no base_url")
    raw_key = str(provider_data.get("api_key") or "dummy")
    key = resolve_provider_api_key(raw_key, preset_id=provider_name) or raw_key
    metadata = dict(provider_data.get("metadata") or {})
    ok, models, err = await probe_provider(base_url, key, metadata)
    if not ok:
        raise RuntimeError(err or f"Could not reach {provider_name}")
    live = [m for m in models if str(m.get("id") or "").strip()]
    if not live:
        raise RuntimeError(f"Provider '{provider_name}' returned no models")
    return live


def replace_provider_models(
    config: Any,
    provider_name: str,
    discovered: list[dict[str, Any]],
) -> RefreshStats:
    """Write discovered ids into the provider and drop stale defaults."""
    name = (provider_name or "").strip()
    pdata = _require_provider(config, name)
    before = [str(m).strip() for m in (pdata.get("available_models") or []) if str(m).strip()]
    live_ids: list[str] = []
    contexts = dict(pdata.get("model_contexts") or {})
    for row in discovered:
        mid = str(row.get("id") or "").strip()
        if not mid or mid in live_ids:
            continue
        live_ids.append(mid)
        ctx = row.get("context_length")
        if ctx:
            try:
                contexts[mid] = int(ctx)
            except (TypeError, ValueError):
                pass
    if not live_ids:
        raise ValueError("discovered model list is empty")

    updated = apply_live_model_ids(pdata, live_ids)
    live_set = set(live_ids)
    updated["model_contexts"] = {k: v for k, v in contexts.items() if k in live_set}
    providers = _provider_map(config)
    providers[name] = updated
    config.providers = providers

    default_model = str(updated.get("default_model") or "")
    if getattr(config, "default_provider", None) == name and default_model:
        config.model = default_model
    _retarget_stale_agent_models(config, name, live_set, default_model)

    after = list(updated.get("available_models") or [])
    return RefreshStats(
        provider=name,
        models=after,
        default_model=default_model,
        added=[m for m in after if m not in before],
        removed=[m for m in before if m not in after],
    )


def set_provider_default_model(config: Any, provider_name: str, model_id: str) -> str:
    """Persist ``default_model`` for a connected provider.

    When the provider is the profile default, also update ``config.model`` and
    the ``main`` agent assignment if it uses this provider.
    """
    name = (provider_name or "").strip()
    model = (model_id or "").strip()
    if not model:
        raise ValueError("model id is empty")
    pdata = _require_provider(config, name)
    available = [str(m).strip() for m in (pdata.get("available_models") or []) if str(m).strip()]
    if model not in available:
        available.append(model)
    pdata["available_models"] = available
    pdata["default_model"] = model
    providers = _provider_map(config)
    providers[name] = pdata
    config.providers = providers

    if getattr(config, "default_provider", None) == name:
        config.model = model
        _sync_main_agent(config, name, model)
    return model


async def refresh_provider_config(config: Any, provider_name: str) -> RefreshStats:
    """Discover models and write them onto ``config`` (caller saves)."""
    pdata = _require_provider(config, provider_name)
    discovered = await discover_provider_models(provider_name.strip(), pdata)
    return replace_provider_models(config, provider_name, discovered)


def _sync_main_agent(config: Any, provider_name: str, model_id: str) -> None:
    agent_models = dict(getattr(config, "agent_models", None) or {})
    main = agent_models.get("main")
    if not isinstance(main, dict):
        return
    if str(main.get("provider") or "") != provider_name:
        return
    updated = dict(main)
    updated["model"] = model_id
    agent_models["main"] = updated
    config.agent_models = agent_models


def _retarget_stale_agent_models(
    config: Any,
    provider_name: str,
    live_ids: set[str],
    new_default: str,
) -> None:
    if not new_default:
        return
    agent_models = dict(getattr(config, "agent_models", None) or {})
    changed = False
    for agent_name, data in list(agent_models.items()):
        if not isinstance(data, dict):
            continue
        if str(data.get("provider") or "") != provider_name:
            continue
        model = str(data.get("model") or "").strip()
        if model and model not in live_ids:
            updated = dict(data)
            updated["model"] = new_default
            agent_models[agent_name] = updated
            changed = True
    if changed:
        config.agent_models = agent_models
