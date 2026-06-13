"""Telegram bot administrator — single user; assigned via bootstrap or CLI."""

from __future__ import annotations

from integrations.messenger.admin import (
    clear_admin_user as _clear_admin_user,
)
from integrations.messenger.admin import (
    load_admin_holix_profile as _load_admin_holix_profile,
)
from integrations.messenger.admin import (
    load_admin_user_id as _load_admin_user_id,
)
from integrations.messenger.admin import (
    set_admin_user as _set_admin_user,
)
from integrations.messenger.platforms import TELEGRAM_PLATFORM

_PLATFORM = TELEGRAM_PLATFORM
ENV_ADMIN_USER_ID = _PLATFORM.admin_user_id_key
ENV_ADMIN_PROFILE = _PLATFORM.admin_profile_key
DEFAULT_ADMIN_PROFILE = _PLATFORM.default_admin_profile


def load_admin_user_id(bot_profile: str) -> int | None:
    return _load_admin_user_id(_PLATFORM, bot_profile)


def load_admin_holix_profile(bot_profile: str) -> str:
    return _load_admin_holix_profile(_PLATFORM, bot_profile)


def set_admin_user(
    bot_profile: str,
    user_id: int,
    *,
    holix_profile: str | None = None,
) -> None:
    _set_admin_user(_PLATFORM, bot_profile, user_id, holix_profile=holix_profile)


def clear_admin_user(bot_profile: str) -> bool:
    return _clear_admin_user(_PLATFORM, bot_profile)