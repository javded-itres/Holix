"""Who may see which Holix profiles in a shared MAX bot."""

from __future__ import annotations

from integrations.max.admin import is_max_admin


def is_profile_list_hidden(bot_profile: str, user_id: int | None) -> bool:
    """Non-admins in multi-tenant mode must not browse other users' profiles."""
    if user_id is None:
        return False
    from integrations.max.config import load_max_settings

    settings = load_max_settings(bot_profile)
    if settings.allow_all:
        return False
    return not is_max_admin(bot_profile, int(user_id))


def list_visible_profiles(
    bot_profile: str,
    user_id: int | None,
    *,
    current: str,
) -> list[str]:
    """Profiles the user may pick from UI or `/profile` without a key."""
    from cli.core import ProfileManager

    if not is_profile_list_hidden(bot_profile, user_id):
        return ProfileManager().list_profiles()

    from integrations.max.user_profiles import resolve_user_profile

    visible: list[str] = []
    mapped = resolve_user_profile(bot_profile, int(user_id)) if user_id is not None else None
    if mapped:
        visible.append(mapped)
    elif current:
        visible.append(current)
    return visible or ([current] if current else [])