"""Profile lifecycle helpers (delete with user notification)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from cli.core import ProfileManager

logger = logging.getLogger(__name__)

PROTECTED_PROFILES = frozenset({"default", "docs", "global"})


@dataclass(slots=True)
class ProfileDeleteResult:
    profile: str
    deleted: bool = False
    notified: list[int] = field(default_factory=list)
    notify_failed: list[tuple[int, str]] = field(default_factory=list)
    mappings_removed: int = 0
    error: str | None = None


def find_telegram_users_for_profile(target_profile: str) -> list[tuple[str, int]]:
    """Return ``(bot_profile, telegram_user_id)`` pairs bound to *target_profile*."""
    from integrations.telegram.user_profiles import load_user_profiles

    name = target_profile.strip()
    if not name:
        return []
    manager = ProfileManager()
    hits: list[tuple[str, int]] = []
    for bot_profile in manager.list_profiles():
        for uid, mapped in load_user_profiles(bot_profile).items():
            if mapped == name:
                hits.append((bot_profile, int(uid)))
    return hits


def format_profile_deletion_message(profile: str) -> str:
    from integrations.telegram.markdown import escape_html

    profile_esc = escape_html(profile)
    return "\n".join(
        [
            "⚠️ <b>Профиль Holix удалён</b>",
            "",
            f"Ваш профиль <code>{profile_esc}</code> удалён администратором с сервера.",
            "Данные профиля (память, workspace, настройки) больше недоступны.",
            "",
            "Если нужен новый доступ — отправьте запрос администратору или "
            "используйте /start в боте.",
        ]
    )


async def notify_profile_deletion(
    bot_profile: str,
    user_id: int,
    *,
    deleted_profile: str,
) -> None:
    from integrations.telegram.config import load_telegram_settings
    from integrations.telegram.env_store import load_telegram_env_files
    from integrations.telegram.notify import send_user_message

    load_telegram_env_files(bot_profile)
    token = load_telegram_settings(bot_profile).bot_token.strip()
    if not token:
        raise RuntimeError(f"TELEGRAM_BOT_TOKEN is not configured for bot profile '{bot_profile}'")
    await send_user_message(
        token,
        int(user_id),
        format_profile_deletion_message(deleted_profile),
    )


def notify_profile_deletion_sync(
    bot_profile: str,
    user_id: int,
    *,
    deleted_profile: str,
) -> None:
    import asyncio

    asyncio.run(
        notify_profile_deletion(
            bot_profile,
            user_id,
            deleted_profile=deleted_profile,
        )
    )


def remove_profile_telegram_bindings(target_profile: str) -> int:
    """Drop Telegram user→profile mappings pointing at *target_profile*."""
    from integrations.telegram.user_profiles import load_user_profiles, save_user_profiles

    name = target_profile.strip()
    removed = 0
    manager = ProfileManager()
    for bot_profile in manager.list_profiles():
        mapping = load_user_profiles(bot_profile)
        changed = False
        for uid, mapped in list(mapping.items()):
            if mapped == name:
                del mapping[uid]
                removed += 1
                changed = True
        if changed:
            save_user_profiles(bot_profile, mapping)
    return removed


def delete_profile_with_notification(
    profile: str,
    *,
    notify: bool = True,
    manager: ProfileManager | None = None,
) -> ProfileDeleteResult:
    """Notify mapped Telegram users, then delete the profile directory."""
    result = ProfileDeleteResult(profile=profile)
    name = profile.strip()
    if not name:
        result.error = "Profile name is required"
        return result
    if name in PROTECTED_PROFILES:
        result.error = f"Cannot delete protected profile '{name}'"
        return result

    mgr = manager or ProfileManager()
    if not mgr.profile_exists(name):
        result.error = f"Profile '{name}' not found"
        return result

    bindings = find_telegram_users_for_profile(name)
    if notify and bindings:
        seen: set[int] = set()
        for bot_profile, uid in bindings:
            if uid in seen:
                continue
            seen.add(uid)
            try:
                notify_profile_deletion_sync(bot_profile, uid, deleted_profile=name)
                result.notified.append(uid)
            except Exception as exc:
                logger.warning(
                    "Failed to notify user %s about deletion of profile '%s': %s",
                    uid,
                    name,
                    exc,
                )
                result.notify_failed.append((uid, str(exc)))

    result.mappings_removed = remove_profile_telegram_bindings(name)

    try:
        from core.crypto.runtime_cache import wipe_profile_runtime_cache

        wipe_profile_runtime_cache(name)
    except Exception as exc:
        logger.debug("Runtime cache wipe failed for %s: %s", name, exc)

    if not mgr.delete_profile(name):
        result.error = f"Failed to delete profile '{name}'"
        return result

    result.deleted = True
    return result