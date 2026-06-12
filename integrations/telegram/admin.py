"""Telegram bot administrator — single user, CLI-only assignment."""

from __future__ import annotations

import os

from integrations.telegram.env_store import read_telegram_env_values, save_telegram_env

ENV_ADMIN_USER_ID = "HOLIX_TELEGRAM_ADMIN_USER_ID"
ENV_ADMIN_PROFILE = "HOLIX_TELEGRAM_ADMIN_PROFILE"
DEFAULT_ADMIN_PROFILE = "admin"


def load_admin_user_id(bot_profile: str) -> int | None:
    from integrations.telegram.env_store import load_telegram_env_files

    load_telegram_env_files(bot_profile)
    raw = read_telegram_env_values(bot_profile).get(ENV_ADMIN_USER_ID, "").strip()
    if raw.isdigit():
        return int(raw)
    return None


def load_admin_holix_profile(bot_profile: str) -> str:
    from integrations.telegram.env_store import load_telegram_env_files

    load_telegram_env_files(bot_profile)
    raw = read_telegram_env_values(bot_profile).get(ENV_ADMIN_PROFILE, "").strip()
    return raw or DEFAULT_ADMIN_PROFILE


def set_admin_user(bot_profile: str, user_id: int, *, holix_profile: str | None = None) -> None:
    """Persist the single Telegram admin (CLI only — never call from bot handlers)."""
    values = read_telegram_env_values(bot_profile)
    values[ENV_ADMIN_USER_ID] = str(int(user_id))
    values[ENV_ADMIN_PROFILE] = (holix_profile or DEFAULT_ADMIN_PROFILE).strip() or DEFAULT_ADMIN_PROFILE
    save_telegram_env(values, profile=bot_profile)


def clear_admin_user(bot_profile: str) -> bool:
    values = read_telegram_env_values(bot_profile)
    if ENV_ADMIN_USER_ID not in values and ENV_ADMIN_PROFILE not in values:
        return False
    values.pop(ENV_ADMIN_USER_ID, None)
    values.pop(ENV_ADMIN_PROFILE, None)
    save_telegram_env(values, profile=bot_profile)
    os.environ.pop(ENV_ADMIN_USER_ID, None)
    os.environ.pop(ENV_ADMIN_PROFILE, None)
    return True