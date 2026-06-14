"""Manage ``HOLIX_TELEGRAM_ALLOWED_USERS`` for a bot profile."""

from __future__ import annotations

from integrations.messenger.allowlist import (
    add_allowed_user as _add_allowed_user,
)
from integrations.messenger.allowlist import (
    format_allowed_user_ids,
)
from integrations.messenger.allowlist import (
    load_allowed_user_ids as _load_allowed_user_ids,
)
from integrations.messenger.allowlist import (
    remove_allowed_user as _remove_allowed_user,
)
from integrations.messenger.platforms import TELEGRAM_PLATFORM

_PLATFORM = TELEGRAM_PLATFORM

__all__ = [
    "add_allowed_user",
    "format_allowed_user_ids",
    "load_allowed_user_ids",
    "remove_allowed_user",
]


def load_allowed_user_ids(bot_profile: str) -> set[int]:
    return _load_allowed_user_ids(_PLATFORM, bot_profile)


def add_allowed_user(bot_profile: str, user_id: int) -> str:
    return _add_allowed_user(_PLATFORM, bot_profile, user_id)


def remove_allowed_user(bot_profile: str, user_id: int) -> str | None:
    return _remove_allowed_user(_PLATFORM, bot_profile, user_id)