"""Telegram-specific profile access (allowlist replaces interactive profile key)."""

from __future__ import annotations

from integrations.telegram.allowlist import load_allowed_user_ids
from integrations.telegram.user_profiles import resolve_user_profile


def telegram_user_may_access_profile(
    bot_profile: str,
    telegram_user_id: int,
    holix_profile: str,
) -> bool:
    """Return True if this Telegram user may use the Holix profile without a key."""
    bot_profile = (bot_profile or "default").strip() or "default"
    holix_profile = holix_profile.strip()
    uid = int(telegram_user_id)

    if not _telegram_user_allowed(bot_profile, uid):
        return False

    mapped = resolve_user_profile(bot_profile, uid)
    if mapped:
        return mapped == holix_profile
    return holix_profile == bot_profile


def _telegram_user_allowed(bot_profile: str, user_id: int) -> bool:
    uid = int(user_id)
    if uid in load_allowed_user_ids(bot_profile):
        return True
    return resolve_user_profile(bot_profile, uid) is not None


def authorize_telegram_profile_access(
    bot_profile: str,
    telegram_user_id: int,
    holix_profile: str,
) -> bool:
    """Mark a profile unlocked for an authorized Telegram session."""
    if not telegram_user_may_access_profile(bot_profile, telegram_user_id, holix_profile):
        return False
    from cli import core as cli_core

    cli_core._unlocked_profiles.add(holix_profile.strip())
    return True


def init_profile_for_telegram(
    holix_profile: str,
    *,
    bot_profile: str,
    telegram_user_id: int,
    profile_key: str | None = None,
):
    """Initialize profile for a Telegram session without an interactive key prompt."""
    from cli.core import init_profile

    authorize_telegram_profile_access(bot_profile, telegram_user_id, holix_profile)
    import os

    from core.crypto.profile_crypto import profile_has_crypto_metadata

    unlock_key = os.getenv("HOLIX_UNLOCK_KEY", "").strip() or None
    if unlock_key and not profile_has_crypto_metadata(holix_profile):
        unlock_key = None
    return init_profile(
        holix_profile,
        profile_key=profile_key,
        unlock_key=unlock_key,
        prompt_key=False,
    )