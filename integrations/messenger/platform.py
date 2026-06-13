"""Messenger platform descriptor — env keys, filenames, validators."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field


def _telegram_token_valid(token: str) -> bool:
    return bool(re.compile(r"^\d+:[A-Za-z0-9_-]{20,}$").match(token.strip()))


def _max_token_valid(token: str) -> bool:
    t = token.strip()
    return len(t) >= 16 and " " not in t


def _telegram_mask(token: str) -> str:
    t = token.strip()
    if not t or ":" not in t:
        return "(not set)"
    bot_id, secret = t.split(":", 1)
    if len(secret) <= 8:
        return f"{bot_id}:***"
    return f"{bot_id}:{secret[:4]}…{secret[-4:]}"


def _max_mask(token: str) -> str:
    t = token.strip()
    if not t:
        return "(not set)"
    if len(t) <= 8:
        return "***"
    return f"{t[:4]}…{t[-4:]}"


@dataclass(frozen=True, slots=True)
class MessengerPlatform:
    """Configuration for a messenger integration (Telegram, MAX, …)."""

    name: str
    env_filename: str
    users_filename: str
    access_requests_filename: str

    token_key: str
    legacy_keys: tuple[tuple[str, str], ...] = ()
    allowed_users_key: str = ""
    allow_all_key: str = ""
    access_requests_key: str = ""
    admin_user_id_key: str = ""
    admin_profile_key: str = ""
    user_profiles_key: str = ""
    profile_key: str = ""
    edit_interval_key: str = ""

    default_admin_profile: str = "admin"
    env_header: str = ""
    env_key_order: tuple[str, ...] = field(default_factory=tuple)

    token_valid: Callable[[str], bool] = _max_token_valid
    token_mask: Callable[[str], str] = _max_mask

    def env_key_aliases(self, canonical: str) -> tuple[str, ...]:
        aliases = [canonical]
        for key, legacy in self.legacy_keys:
            if key == canonical:
                aliases.append(legacy)
        return tuple(dict.fromkeys(aliases))