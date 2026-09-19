"""Single messenger bot administrator — assigned via CLI."""

from __future__ import annotations

import os

from integrations.messenger.env_store import (
    load_messenger_env_files,
    read_messenger_env_values,
    save_messenger_env,
)
from integrations.messenger.platform import MessengerPlatform


def _normalize_env_raw(raw: str | None) -> str:
    """Strip whitespace and optional surrounding quotes from dotenv values."""
    text = (raw or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text


TELEGRAM_EXTRA_ADMIN_IDS_KEY = "HOLIX_TELEGRAM_ADMIN_EXTRA_USER_IDS"


def parse_messenger_user_ids(raw: str | None) -> list[int]:
    """Parse comma/space-separated numeric user ids."""
    from core.runtime.admin_support import parse_telegram_user_ids

    return parse_telegram_user_ids(raw)


def load_admin_user_id(platform: MessengerPlatform, bot_profile: str) -> int | None:
    """Load admin Telegram/MAX user id for the bot profile.

    Preference order:
    1. platform messenger env file (``telegram.env`` / ``max.env``)
    2. process environment (profile ``.env`` / systemd) — common on VDS deploys
    """
    load_messenger_env_files(platform, bot_profile)
    raw = _normalize_env_raw(
        read_messenger_env_values(platform, bot_profile).get(
            platform.admin_user_id_key,
            "",
        )
    )
    ids = parse_messenger_user_ids(raw)
    if not ids:
        # Fallback: profile .env is often the source of truth in production
        ids = parse_messenger_user_ids(os.getenv(platform.admin_user_id_key, ""))
    return ids[0] if ids else None


def load_admin_user_ids(platform: MessengerPlatform, bot_profile: str) -> list[int]:
    """Primary admin plus optional extra Telegram admin ids (support tickets)."""
    load_messenger_env_files(platform, bot_profile)
    values = read_messenger_env_values(platform, bot_profile)
    primary_raw = _normalize_env_raw(values.get(platform.admin_user_id_key, ""))
    if not primary_raw:
        primary_raw = _normalize_env_raw(os.getenv(platform.admin_user_id_key, ""))
    ids = parse_messenger_user_ids(primary_raw)
    extra_key = TELEGRAM_EXTRA_ADMIN_IDS_KEY if platform.name == "telegram" else ""
    if extra_key:
        extra_raw = _normalize_env_raw(values.get(extra_key, ""))
        if not extra_raw:
            extra_raw = _normalize_env_raw(os.getenv(extra_key, ""))
        ids.extend(parse_messenger_user_ids(extra_raw))
    return list(dict.fromkeys(ids))


def load_admin_holix_profile(platform: MessengerPlatform, bot_profile: str) -> str:
    load_messenger_env_files(platform, bot_profile)
    raw = _normalize_env_raw(
        read_messenger_env_values(platform, bot_profile).get(
            platform.admin_profile_key,
            "",
        )
    )
    if not raw:
        raw = _normalize_env_raw(os.getenv(platform.admin_profile_key, ""))
    return raw or platform.default_admin_profile


def set_admin_user(
    platform: MessengerPlatform,
    bot_profile: str,
    user_id: int,
    *,
    holix_profile: str | None = None,
) -> None:
    values = read_messenger_env_values(platform, bot_profile)
    values[platform.admin_user_id_key] = str(int(user_id))
    values[platform.admin_profile_key] = (
        holix_profile or platform.default_admin_profile
    ).strip() or platform.default_admin_profile
    save_messenger_env(platform, values, profile=bot_profile)


def clear_admin_user(platform: MessengerPlatform, bot_profile: str) -> bool:
    values = read_messenger_env_values(platform, bot_profile)
    if platform.admin_user_id_key not in values and platform.admin_profile_key not in values:
        return False
    values.pop(platform.admin_user_id_key, None)
    values.pop(platform.admin_profile_key, None)
    if platform.name == "telegram":
        values.pop(TELEGRAM_EXTRA_ADMIN_IDS_KEY, None)
    save_messenger_env(platform, values, profile=bot_profile)
    os.environ.pop(platform.admin_user_id_key, None)
    os.environ.pop(platform.admin_profile_key, None)
    if platform.name == "telegram":
        os.environ.pop(TELEGRAM_EXTRA_ADMIN_IDS_KEY, None)
    return True


def is_messenger_admin(
    platform: MessengerPlatform,
    bot_profile: str,
    actor_user_id: int,
) -> bool:
    admin_id = load_admin_user_id(platform, bot_profile)
    return admin_id is not None and int(admin_id) == int(actor_user_id)
