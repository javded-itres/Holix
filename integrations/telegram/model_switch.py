"""Runtime model selection for Telegram sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING

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


async def apply_provider_model_index(
    host: TelegramHost, provider_idx: int, model_idx: int
) -> str:
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


def _truncate_button(text: str, max_len: int = 28) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"