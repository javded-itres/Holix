"""Runtime model selection for Telegram sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from integrations.telegram.host import TelegramHost

MODELS_PAGE_SIZE = 10
PROVIDERS_PAGE_SIZE = 8


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
    from cli.core import ProfileManager
    from core.models.manager import ModelManager

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
        presets.append(
            ModelChoice(slot_id=name, label=name, provider=mc.provider, model=mc.model)
        )

    providers: list[ProviderMenu] = []
    for pname, pdata in sorted((cfg.providers or {}).items()):
        models: list[str] = []
        default_model = pdata.get("default_model") or ""
        for mid in pdata.get("available_models") or []:
            if mid and mid not in models:
                models.append(mid)
        if default_model and default_model not in models:
            models.insert(0, default_model)
        if not models and default_model:
            models = [default_model]
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
    """Flat list (legacy); prefer :func:`build_models_menu`."""
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
    from cli.core import ProfileManager
    from core.models.manager import ModelConfig, ModelManager

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
    """Switch active LLM on a host (TUI, Telegram, …) without changing profile YAML."""
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
        from core.session_models import host_conversation_id, persist_session_model

        persist_session_model(host, choice)
        from core.session_models import _mark_model_synced

        _mark_model_synced(host, host_conversation_id(host))

    return f"{choice.provider}/{choice.model}"


async def apply_model_choice(host: TelegramHost, choice: ModelChoice) -> str:
    try:
        return apply_model_choice_sync(host, choice)
    except RuntimeError:
        return "Агент не готов"


async def apply_preset_index(host: TelegramHost, index: int) -> str:
    presets = host._session.ui_model_presets
    if index < 0 or index >= len(presets):
        return "Неверный пресет"
    return await apply_model_choice(host, presets[index])


async def apply_provider_model_index(
    host: TelegramHost, provider_idx: int, model_idx: int
) -> str:
    providers = host._session.ui_providers
    if provider_idx < 0 or provider_idx >= len(providers):
        return "Неверный провайдер"
    prov = providers[provider_idx]
    if model_idx < 0 or model_idx >= len(prov.models):
        return "Неверная модель"
    model_id = prov.models[model_idx]
    choice = choice_for_provider_model(prov.name, model_id)
    return await apply_model_choice(host, choice)


def current_model_label(session: Any) -> str:
    if session.active_model_label:
        return session.active_model_label
    if session.agent:
        return session.agent.model
    return "—"


def is_slot_active(session: Any, slot_id: str) -> bool:
    return session.active_model_slot == slot_id


def _truncate_button(text: str, max_len: int = 28) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"