"""Manage messenger allowlist env key for a bot profile."""

from __future__ import annotations

from integrations.messenger.env_store import (
    load_messenger_env_files,
    read_messenger_env_values,
    save_messenger_env,
)
from integrations.messenger.platform import MessengerPlatform


def load_allowed_user_ids(platform: MessengerPlatform, bot_profile: str) -> set[int]:
    load_messenger_env_files(platform, bot_profile)
    raw = read_messenger_env_values(platform, bot_profile).get(
        platform.allowed_users_key,
        "",
    )
    out: set[int] = set()
    for part in raw.replace(" ", "").split(","):
        if part.isdigit():
            out.add(int(part))
    return out


def format_allowed_user_ids(user_ids: set[int]) -> str:
    return ",".join(str(uid) for uid in sorted(user_ids))


def add_allowed_user(platform: MessengerPlatform, bot_profile: str, user_id: int) -> str:
    values = read_messenger_env_values(platform, bot_profile)
    allowed = load_allowed_user_ids(platform, bot_profile)
    allowed.add(int(user_id))
    text = format_allowed_user_ids(allowed)
    values[platform.allowed_users_key] = text
    save_messenger_env(platform, values, profile=bot_profile)
    return text


def remove_allowed_user(
    platform: MessengerPlatform,
    bot_profile: str,
    user_id: int,
) -> str | None:
    values = read_messenger_env_values(platform, bot_profile)
    allowed = load_allowed_user_ids(platform, bot_profile)
    if int(user_id) not in allowed:
        return None
    allowed.remove(int(user_id))
    text = format_allowed_user_ids(allowed)
    if text:
        values[platform.allowed_users_key] = text
    else:
        values.pop(platform.allowed_users_key, None)
    save_messenger_env(platform, values, profile=bot_profile)
    return text