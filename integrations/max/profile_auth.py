"""MAX-specific profile access (allowlist replaces interactive profile key)."""

from __future__ import annotations

from integrations.max.allowlist import load_allowed_user_ids
from integrations.max.user_profiles import resolve_user_profile


def max_user_may_access_profile(
    bot_profile: str,
    max_user_id: int,
    holix_profile: str,
) -> bool:
    bot_profile = (bot_profile or "default").strip() or "default"
    holix_profile = holix_profile.strip()
    uid = int(max_user_id)

    if not _max_user_allowed(bot_profile, uid):
        return False

    mapped = resolve_user_profile(bot_profile, uid)
    if mapped:
        return mapped == holix_profile
    return holix_profile == bot_profile


def _max_user_allowed(bot_profile: str, user_id: int) -> bool:
    uid = int(user_id)
    if uid in load_allowed_user_ids(bot_profile):
        return True
    return resolve_user_profile(bot_profile, uid) is not None


def authorize_max_profile_access(
    bot_profile: str,
    max_user_id: int,
    holix_profile: str,
) -> bool:
    if not max_user_may_access_profile(bot_profile, max_user_id, holix_profile):
        return False
    from cli import core as cli_core

    cli_core._unlocked_profiles.add(holix_profile.strip())
    return True