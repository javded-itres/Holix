"""MAX user id → Holix profile bindings (shared bot)."""

from __future__ import annotations

from integrations.messenger.platforms import MAX_PLATFORM
from integrations.messenger.user_profiles import (
    format_user_profiles_text,
    parse_user_profiles_text,
    validate_user_profiles_text,
)
from integrations.messenger.user_profiles import (
    load_user_profiles as _load_user_profiles,
)
from integrations.messenger.user_profiles import (
    remove_user_profile as _remove_user_profile,
)
from integrations.messenger.user_profiles import (
    resolve_user_profile as _resolve_user_profile,
)
from integrations.messenger.user_profiles import (
    save_user_profiles as _save_user_profiles,
)
from integrations.messenger.user_profiles import (
    set_user_profile as _set_user_profile,
)
from integrations.messenger.user_profiles import (
    users_mapping_path,
)

_PLATFORM = MAX_PLATFORM
ENV_KEY = _PLATFORM.user_profiles_key
MAX_USERS_FILE = _PLATFORM.users_filename


def max_users_path(bot_profile: str):
    return users_mapping_path(_PLATFORM, bot_profile)


def load_user_profiles(bot_profile: str) -> dict[int, str]:
    return _load_user_profiles(_PLATFORM, bot_profile)


def save_user_profiles(bot_profile: str, mapping: dict[int, str]):
    return _save_user_profiles(_PLATFORM, bot_profile, mapping)


def resolve_user_profile(bot_profile: str, user_id: int) -> str | None:
    return _resolve_user_profile(_PLATFORM, bot_profile, user_id)


def set_user_profile(bot_profile: str, user_id: int, profile: str):
    return _set_user_profile(_PLATFORM, bot_profile, user_id, profile)


def remove_user_profile(bot_profile: str, user_id: int):
    return _remove_user_profile(_PLATFORM, bot_profile, user_id)