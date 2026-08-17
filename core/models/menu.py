"""Runtime model selection menus — shared by hosts (TUI, Telegram, Studio)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ModelChoice:
    """One selectable model slot."""

    slot_id: str
    label: str
    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class ProviderMenu:
    """Provider with full model list for nested picker."""

    name: str
    models: tuple[str, ...]
    default_model: str | None = None


@dataclass(frozen=True, slots=True)
class ModelsMenuState:
    """Root models menu: presets + providers."""

    presets: tuple[ModelChoice, ...]
    providers: tuple[ProviderMenu, ...]


def build_models_menu(profile: str) -> ModelsMenuState:
    """Presets (main, agent_models) + per-provider model lists."""
    from core.models.manager import ModelManager
    from core.profile import ProfileManager

    try:
        cfg = ProfileManager().load_profile(profile)
    except Exception:
        return ModelsMenuState(presets=(), providers=())

    mm = ModelManager(cfg)
    presets: list[ModelChoice] = []
    seen: set[tuple[str, str]] = set()

    default = mm.get_default_model_config()
    if default:
        key = (default.provider, default.model)
        seen.add(key)
        presets.append(
            ModelChoice(
                slot_id="main",
                label="main",
                provider=default.provider,
                model=default.model,
            )
        )

    for name in sorted((cfg.agent_models or {}).keys()):
        mc = mm.get_agent_model_config(name)
        if not mc:
            continue
        key = (mc.provider, mc.model)
        if key in seen:
            continue
        seen.add(key)
        presets.append(ModelChoice(slot_id=name, label=name, provider=mc.provider, model=mc.model))

    providers: list[ProviderMenu] = []
    for pname, pdata in sorted((cfg.providers or {}).items()):
        models: list[str] = []
        default_model = pdata.get("default_model") or ""
        for mid in pdata.get("available_models") or []:
            if mid and mid not in models:
                models.append(mid)
        # Do not inject default_model if it is not in the live available list —
        # that re-surfaces stale aliases (qwen3.8-27b-mac1, etc.).
        if models:
            providers.append(
                ProviderMenu(
                    name=pname,
                    models=tuple(models),
                    default_model=default_model or None,
                )
            )

    if not presets and cfg.model:
        presets.append(
            ModelChoice(
                slot_id="legacy",
                label="default",
                provider="legacy",
                model=cfg.model,
            )
        )

    return ModelsMenuState(presets=tuple(presets), providers=tuple(providers))


def build_model_choices(profile: str, *, max_provider_models: int = 8) -> list[ModelChoice]:
    state = build_models_menu(profile)
    flat: list[ModelChoice] = list(state.presets)
    seen = {(c.provider, c.model) for c in flat}
    for prov in state.providers:
        for mid in prov.models[:max_provider_models]:
            key = (prov.name, mid)
            if key in seen:
                continue
            seen.add(key)
            flat.append(
                ModelChoice(
                    slot_id=f"prov:{prov.name}:{mid}",
                    label=mid,
                    provider=prov.name,
                    model=mid,
                )
            )
    return flat


def choice_for_provider_model(provider: str, model_id: str) -> ModelChoice:
    return ModelChoice(
        slot_id=f"prov:{provider}:{model_id}",
        label=model_id,
        provider=provider,
        model=model_id,
    )


def resolve_model_config(profile: str, choice: ModelChoice) -> Any:
    from core.models.manager import ModelConfig, ModelManager
    from core.profile import ProfileManager

    cfg = ProfileManager().load_profile(profile)
    mm = ModelManager(cfg)

    if choice.slot_id == "main":
        mc = mm.get_default_model_config()
    elif choice.slot_id in (cfg.agent_models or {}):
        mc = mm.get_agent_model_config(choice.slot_id)
    elif choice.slot_id.startswith("prov:"):
        parts = choice.slot_id.split(":", 2)
        if len(parts) != 3:
            raise ValueError(f"invalid slot: {choice.slot_id}")
        _, pname, model_id = parts
        pdata = (cfg.providers or {}).get(pname)
        if not pdata:
            raise ValueError(f"unknown provider: {pname}")
        model_contexts = pdata.get("model_contexts", {})
        context_window = model_contexts.get(model_id) if model_contexts else None
        if not context_window and cfg.context_window:
            context_window = cfg.context_window
        mc = ModelConfig(
            provider=pname,
            model=model_id,
            base_url=pdata.get("base_url", ""),
            api_key=pdata.get("api_key", "dummy"),
            temperature=cfg.temperature,
            context_window=context_window,
        )
    elif choice.slot_id == "legacy":
        mc = ModelConfig(
            provider="legacy",
            model=cfg.model,
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            temperature=cfg.temperature,
            context_window=cfg.context_window,
        )
    else:
        mc = mm.get_agent_model_config(choice.slot_id)

    if not mc:
        raise ValueError("no model configuration")
    return mc


def apply_model_choice_sync(
    host: Any,
    choice: ModelChoice,
    *,
    profile: str | None = None,
    persist: bool = True,
) -> str:
    agent = getattr(host, "agent", None)
    if not agent:
        raise RuntimeError("Agent not ready")

    prof = profile or getattr(host, "profile", "default")
    mc = resolve_model_config(prof, choice)
    agent.set_active_model_config(mc, model_slot_id=choice.slot_id)

    session = getattr(host, "_session", None)
    if session is not None:
        session.active_model_slot = choice.slot_id
        session.active_model_label = choice.label

    if hasattr(host, "_resolved_model"):
        host._resolved_model = mc.model
    if hasattr(host, "active_model_slot"):
        host.active_model_slot = choice.slot_id
    if hasattr(host, "active_model_label"):
        host.active_model_label = choice.label
    if hasattr(host, "_refresh_status_bar"):
        host._refresh_status_bar()

    if persist:
        from core.session_models import (
            _mark_model_synced,
            host_conversation_id,
            persist_session_model,
        )

        persist_session_model(host, choice)
        _mark_model_synced(host, host_conversation_id(host))

    return f"{choice.provider}/{choice.model}"


def current_model_label(session: Any) -> str:
    if session.active_model_label:
        return session.active_model_label
    if session.agent:
        return session.agent.model
    return "—"


def is_slot_active(session: Any, slot_id: str) -> bool:
    return session.active_model_slot == slot_id
