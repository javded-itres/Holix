"""Localized strings for ``holix bootstrap`` and ``install.sh``."""

from __future__ import annotations

from typing import Any

_BOOTSTRAP_MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "welcome_title": "Holix — initial setup",
        "welcome_body": "We will configure LLM and (optionally) Telegram.",
        "llm_title": "LLM connection",
        "llm_body": "Holix uses an OpenAI-compatible API (Ollama, LiteLLM, OpenAI, Groq…).",
        "llm_reconfigure": 'Provider "{name}" is already configured. Reconfigure?',
        "llm_keep": "LLM: kept current provider",
        "llm_preset_ollama": "Ollama (local, OpenAI-compatible)",
        "llm_preset_litellm": "LiteLLM / OpenAI-compatible proxy",
        "llm_preset_openai": "OpenAI API",
        "llm_preset_groq": "Groq",
        "llm_skip_hint": "Skip (later: holix models setup)",
        "llm_choose": "Choose provider",
        "llm_not_configured": "LLM not configured. Run: holix models setup",
        "llm_unknown_preset": "Unknown preset: {id}",
        "llm_probe": "Checking {name}…",
        "llm_probe_failed": "Could not connect: {err} ({url})",
        "llm_save_anyway": "Save settings anyway?",
        "llm_url": "URL: {url}",
        "telegram_title": "Telegram",
        "telegram_body": (
            "1. [@BotFather](https://t.me/BotFather) → /newbot → copy token\n"
            "2. Your Telegram ID: [@userinfobot](https://t.me/userinfobot)\n"
            "3. After setup send /start to the bot"
        ),
        "telegram_configure": "Configure Telegram now?",
        "telegram_skipped": "Telegram skipped. Later: holix telegram setup",
        "telegram_extra_missing": "Telegram extra not installed. Run: pipx install 'Holix[telegram]'",
        "telegram_use_saved": "Use saved bot token?",
        "telegram_token_prompt": "Bot token from @BotFather",
        "telegram_bad_token": "Invalid token format. Expected: 123456789:AAH…",
        "telegram_verify": "Verifying token (getMe)…",
        "telegram_api_error": "Telegram API: {err}",
        "telegram_bot_ok": "Bot: @{name}",
        "telegram_admin_id": "Your Telegram user ID (admin, digits only)",
        "telegram_admin_id_bad": "Numeric Telegram ID required (e.g. from @userinfobot)",
        "telegram_admin_profile": "Holix profile for admin",
        "telegram_saved": "Telegram saved: {path}",
        "telegram_open": "Open https://t.me/{name} and send /start",
        "locale_applied": "UI language: {code} (profiles: {profiles})",
        "skip_llm_non_tty": "LLM skipped (non-interactive). Run: holix models setup",
        "skip_tg_non_tty": "Telegram skipped. Run: holix telegram setup",
        "done_title": "Done",
        "done_next": "Next steps:",
        "done_doctor": "holix doctor",
        "done_tui": "holix tui",
        "done_models": "holix models setup",
        "done_telegram": "holix telegram setup",
        "done_gateway": "holix gateway start --with-docs",
        "lang_menu": "Choose install language / Выберите язык установки",
        "lang_option_en": "1) English",
        "lang_option_ru": "2) Русский",
        "lang_prompt": "Language [1]",
    },
    "ru": {
        "welcome_title": "Holix — первичная настройка",
        "welcome_body": "Настроим LLM и (опционально) Telegram-бота.",
        "llm_title": "Подключение LLM",
        "llm_body": "Holix использует OpenAI-compatible API (Ollama, LiteLLM, OpenAI, Groq…).",
        "llm_reconfigure": "Провайдер «{name}» уже настроен. Перенастроить?",
        "llm_keep": "LLM: оставлен текущий провайдер",
        "llm_preset_ollama": "Ollama (локально, OpenAI-compatible)",
        "llm_preset_litellm": "LiteLLM / OpenAI-совместимый прокси",
        "llm_preset_openai": "OpenAI API",
        "llm_preset_groq": "Groq",
        "llm_skip_hint": "Пропустить (позже: holix models setup)",
        "llm_choose": "Выберите провайдер",
        "llm_not_configured": "LLM не настроен. Запустите: holix models setup",
        "llm_unknown_preset": "Неизвестный пресет: {id}",
        "llm_probe": "Проверка {name}…",
        "llm_probe_failed": "Не удалось подключиться: {err} ({url})",
        "llm_save_anyway": "Сохранить настройки всё равно?",
        "llm_url": "URL: {url}",
        "telegram_title": "Telegram",
        "telegram_body": (
            "1. [@BotFather](https://t.me/BotFather) → /newbot → скопируйте токен\n"
            "2. Ваш Telegram ID: [@userinfobot](https://t.me/userinfobot)\n"
            "3. После установки отправьте боту /start"
        ),
        "telegram_configure": "Настроить Telegram сейчас?",
        "telegram_skipped": "Telegram: пропущено. Позже: holix telegram setup",
        "telegram_extra_missing": "Пакет telegram не установлен. Переустановите: pipx install 'Holix[telegram]'",
        "telegram_use_saved": "Использовать сохранённый токен бота?",
        "telegram_token_prompt": "Токен бота от @BotFather",
        "telegram_bad_token": "Неверный формат токена. Ожидается: 123456789:AAH…",
        "telegram_verify": "Проверка токена (getMe)…",
        "telegram_api_error": "Telegram API: {err}",
        "telegram_bot_ok": "Бот: @{name}",
        "telegram_admin_id": "Ваш Telegram user ID (админ, только цифры)",
        "telegram_admin_id_bad": "Нужен числовой Telegram ID (например из @userinfobot)",
        "telegram_admin_profile": "Holix-профиль для админа",
        "telegram_saved": "Telegram сохранён: {path}",
        "telegram_open": "Откройте https://t.me/{name} и отправьте /start",
        "locale_applied": "Язык интерфейса: {code} (профили: {profiles})",
        "skip_llm_non_tty": "LLM: пропущено (неинтерактивный режим). Запустите: holix models setup",
        "skip_tg_non_tty": "Telegram: пропущено. Запустите: holix telegram setup",
        "done_title": "Готово",
        "done_next": "Дальше:",
        "done_doctor": "holix doctor",
        "done_tui": "holix tui",
        "done_models": "holix models setup",
        "done_telegram": "holix telegram setup",
        "done_gateway": "holix gateway start --with-docs",
        "lang_menu": "Choose install language / Выберите язык установки",
        "lang_option_en": "1) English",
        "lang_option_ru": "2) Русский",
        "lang_prompt": "Язык [1]",
    },
}


def bt(key: str, lang: str, **kwargs: Any) -> str:
    """Bootstrap translation."""
    catalog = _BOOTSTRAP_MESSAGES.get(lang) or _BOOTSTRAP_MESSAGES["en"]
    template = catalog.get(key) or _BOOTSTRAP_MESSAGES["en"].get(key) or key
    if kwargs:
        return template.format(**kwargs)
    return template


def bootstrap_preset_labels(lang: str) -> tuple[tuple[str, str], ...]:
    return (
        ("ollama", bt("llm_preset_ollama", lang)),
        ("litellm", bt("llm_preset_litellm", lang)),
        ("openai", bt("llm_preset_openai", lang)),
        ("groq", bt("llm_preset_groq", lang)),
    )