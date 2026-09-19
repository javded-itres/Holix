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
    load_admin_user_ids as _load_admin_user_ids,
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


def load_admin_user_ids(bot_profile: str) -> list[int]:
    return _load_admin_user_ids(_PLATFORM, bot_profile)


def list_telegram_support_admins(preferred_profile: str = "default") -> list[dict[str, int | str]]:
    """Telegram bot profile + admin user ids that should receive support tickets.

    Dedupes the same bot token + admin id when several Holix profiles share a bot.
    Prefers *preferred_profile* so the bot the user is talking to is used first.
    """
    from core.profile import ProfileManager

    from integrations.telegram.config import load_telegram_settings

    manager = ProfileManager()
    names = list(manager.list_profiles())
    prefer = (preferred_profile or "").strip()
    if prefer and prefer in names:
        names = [prefer] + [n for n in names if n != prefer]
    seen: set[tuple[str, int]] = set()
    out: list[dict[str, int | str]] = []
    for name in names:
        try:
            settings = load_telegram_settings(name)
        except Exception:
            continue
        token = str(getattr(settings, "bot_token", "") or "").strip()
        if not token:
            continue
        token_key = token[-12:]
        for uid in load_admin_user_ids(name):
            key = (token_key, int(uid))
            if key in seen:
                continue
            seen.add(key)
            out.append({"profile": name, "user_id": int(uid)})
    return out


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
