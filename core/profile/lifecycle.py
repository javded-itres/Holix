"""Profile lifecycle helpers (delete with optional messenger notification via hooks)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from core.plugins.hooks import profile_lifecycle_hooks
from core.profile import ProfileManager

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
    finder = profile_lifecycle_hooks.find_telegram_users
    if finder is None:
        return []
    return finder(target_profile)


def format_profile_deletion_message(profile: str) -> str:
    fmt = profile_lifecycle_hooks.format_deletion_message
    if fmt is not None:
        return fmt(profile)
    return (
        f"Profile '{profile}' was deleted by an administrator. "
        "Profile data is no longer available."
    )


def notify_profile_deletion_sync(
    bot_profile: str,
    user_id: int,
    *,
    deleted_profile: str,
) -> None:
    notify = profile_lifecycle_hooks.notify_deletion_sync
    if notify is None:
        raise RuntimeError("Profile deletion notification hooks are not registered")
    notify(bot_profile, user_id, deleted_profile)


def remove_profile_telegram_bindings(target_profile: str) -> int:
    """Drop Telegram user→profile mappings pointing at *target_profile*."""
    remover = profile_lifecycle_hooks.remove_bindings
    if remover is None:
        return 0
    return remover(target_profile)


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
