"""Runtime model selection for Telegram sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.menu import (
    ModelChoice,
    ModelsMenuState,
    ProviderMenu,
    apply_model_choice_sync,
    build_model_choices,
    build_models_menu,
    choice_for_provider_model,
    current_model_label,
    is_slot_active,
    resolve_model_config,
)

if TYPE_CHECKING:
    from integrations.telegram.host import TelegramHost

MODELS_PAGE_SIZE = 10
PROVIDERS_PAGE_SIZE = 8

__all__ = [
    "MODELS_PAGE_SIZE",
    "PROVIDERS_PAGE_SIZE",
    "ModelChoice",
    "ModelsMenuState",
    "ProviderMenu",
    "apply_model_choice",
    "apply_model_choice_sync",
    "apply_preset_index",
    "apply_provider_model_index",
    "refresh_provider_at",
    "reload_provider_menu",
    "set_provider_default_at",
    "build_model_choices",
    "build_models_menu",
    "choice_for_provider_model",
    "current_model_label",
    "is_slot_active",
    "resolve_model_config",
]


async def apply_model_choice(host: TelegramHost, choice: ModelChoice) -> str:
    try:
        return apply_model_choice_sync(host, choice)
    except RuntimeError:
        from core.i18n import t

        from integrations.messenger.locale import messenger_host_locale

        return t("tg.agent_not_ready", messenger_host_locale(host))


async def apply_preset_index(host: TelegramHost, index: int) -> str:
    presets = host._session.ui_model_presets
    if index < 0 or index >= len(presets):
        from core.i18n import t

        from integrations.messenger.locale import messenger_host_locale

        return t("tg.invalid_preset", messenger_host_locale(host))
    return await apply_model_choice(host, presets[index])


async def apply_provider_model_index(host: TelegramHost, provider_idx: int, model_idx: int) -> str:
    providers = host._session.ui_providers
    if provider_idx < 0 or provider_idx >= len(providers):
        from core.i18n import t

        from integrations.messenger.locale import messenger_host_locale

        return t("tg.invalid_provider", messenger_host_locale(host))
    prov = providers[provider_idx]
    if model_idx < 0 or model_idx >= len(prov.models):
        from core.i18n import t

        from integrations.messenger.locale import messenger_host_locale

        return t("tg.invalid_model", messenger_host_locale(host))
    model_id = prov.models[model_idx]
    choice = choice_for_provider_model(prov.name, model_id)
    return await apply_model_choice(host, choice)


def _profile_config(host: Any):
    cfg = getattr(host, "config", None)
    if cfg is not None and getattr(cfg, "providers", None) is not None:
        return cfg, False
    from core.profile import ProfileManager

    return ProfileManager().load_profile(getattr(host, "profile", "default")), True


def _save_profile_config(host: Any, config: Any, *, loaded_fresh: bool) -> None:
    from core.profile import ProfileManager

    profile = getattr(host, "profile", "default")
    ProfileManager().save_profile(profile, config)
    if loaded_fresh:
        host_cfg = getattr(host, "config", None)
        if host_cfg is not None and host_cfg is not config:
            for field in ("providers", "model", "default_provider", "agent_models"):
                if hasattr(config, field):
                    setattr(host_cfg, field, getattr(config, field))


def reload_provider_menu(host: Any, provider_name: str) -> int | None:
    """Reload cached menus from disk and return the provider's new index."""
    state = build_models_menu(getattr(host, "profile", "default"))
    session = host._session
    session.ui_model_presets = list(state.presets)
    session.ui_providers = list(state.providers)
    for i, prov in enumerate(state.providers):
        if prov.name == provider_name:
            session.ui_models_provider_idx = i
            return i
    session.ui_models_provider_idx = None
    return None


async def refresh_provider_at(host: Any, provider_idx: int) -> tuple[int | None, str]:
    """Probe the provider, persist ``available_models``, reload the menu."""
    from core.models.provider_models import refresh_provider_config

    providers = host._session.ui_providers
    if provider_idx < 0 or provider_idx >= len(providers):
        from core.i18n import t

        from integrations.messenger.locale import messenger_host_locale

        return None, t("tg.invalid_provider", messenger_host_locale(host))
    name = providers[provider_idx].name
    config, loaded_fresh = _profile_config(host)
    try:
        stats = await refresh_provider_config(config, name)
    except (RuntimeError, ValueError) as exc:
        return provider_idx, str(exc)[:180]
    _save_profile_config(host, config, loaded_fresh=loaded_fresh)
    new_idx = reload_provider_menu(host, name)
    added = len(stats.added)
    removed = len(stats.removed)
    return new_idx, f"{name}: {len(stats.models)} (+{added}/-{removed})"


async def set_provider_default_at(host: Any, provider_idx: int, model_idx: int) -> str:
    """Persist the provider default and switch the current chat to it."""
    from core.models.provider_models import set_provider_default_model

    providers = host._session.ui_providers
    if provider_idx < 0 or provider_idx >= len(providers):
        from core.i18n import t

        from integrations.messenger.locale import messenger_host_locale

        return t("tg.invalid_provider", messenger_host_locale(host))
    prov = providers[provider_idx]
    if model_idx < 0 or model_idx >= len(prov.models):
        from core.i18n import t

        from integrations.messenger.locale import messenger_host_locale

        return t("tg.invalid_model", messenger_host_locale(host))
    model_id = prov.models[model_idx]
    config, loaded_fresh = _profile_config(host)
    try:
        set_provider_default_model(config, prov.name, model_id)
    except ValueError as exc:
        return str(exc)[:180]
    _save_profile_config(host, config, loaded_fresh=loaded_fresh)
    reload_provider_menu(host, prov.name)
    choice = choice_for_provider_model(prov.name, model_id)
    label = await apply_model_choice(host, choice)
    return f"default {label}"


def _truncate_button(text: str, max_len: int = 28) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
