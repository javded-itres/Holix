"""Single messenger bot administrator — assigned via CLI."""

from __future__ import annotations

import os

from integrations.messenger.env_store import (
    load_messenger_env_files,
    read_messenger_env_values,
    save_messenger_env,
)
from integrations.messenger.platform import MessengerPlatform


def load_admin_user_id(platform: MessengerPlatform, bot_profile: str) -> int | None:
    load_messenger_env_files(platform, bot_profile)
    raw = read_messenger_env_values(platform, bot_profile).get(
        platform.admin_user_id_key,
        "",
    ).strip()
    if raw.isdigit():
        return int(raw)
    return None


def load_admin_holix_profile(platform: MessengerPlatform, bot_profile: str) -> str:
    load_messenger_env_files(platform, bot_profile)
    raw = read_messenger_env_values(platform, bot_profile).get(
        platform.admin_profile_key,
        "",
    ).strip()
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
        (holix_profile or platform.default_admin_profile).strip()
        or platform.default_admin_profile
    )
    save_messenger_env(platform, values, profile=bot_profile)


def clear_admin_user(platform: MessengerPlatform, bot_profile: str) -> bool:
    values = read_messenger_env_values(platform, bot_profile)
    if (
        platform.admin_user_id_key not in values
        and platform.admin_profile_key not in values
    ):
        return False
    values.pop(platform.admin_user_id_key, None)
    values.pop(platform.admin_profile_key, None)
    save_messenger_env(platform, values, profile=bot_profile)
    os.environ.pop(platform.admin_user_id_key, None)
    os.environ.pop(platform.admin_profile_key, None)
    return True


def is_messenger_admin(
    platform: MessengerPlatform,
    bot_profile: str,
    actor_user_id: int,
) -> bool:
    admin_id = load_admin_user_id(platform, bot_profile)
    return admin_id is not None and int(admin_id) == int(actor_user_id)