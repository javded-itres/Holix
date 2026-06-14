"""Remove MAX users from allowlist, profile map, and access requests."""

from __future__ import annotations

from integrations.messenger.platforms import MAX_PLATFORM
from integrations.messenger.user_removal import (
    MessengerUserRemovalResult,
)
from integrations.messenger.user_removal import (
    list_known_user_ids as _list_known_user_ids,
)
from integrations.messenger.user_removal import (
    remove_messenger_user as _remove_messenger_user,
)

_PLATFORM = MAX_PLATFORM

__all__ = [
    "MessengerUserRemovalResult",
    "list_known_user_ids",
    "remove_max_user",
]


def list_known_user_ids(bot_profile: str) -> dict[int, dict[str, str]]:
    return _list_known_user_ids(_PLATFORM, bot_profile)


def remove_max_user(
    bot_profile: str,
    user_id: int,
    *,
    notify: bool = True,
    force_admin: bool = False,
) -> MessengerUserRemovalResult:
    from integrations.max.notify import notify_access_revoked_sync

    return _remove_messenger_user(
        _PLATFORM,
        bot_profile,
        user_id,
        notify=notify,
        force_admin=force_admin,
        notify_revoked_sync=notify_access_revoked_sync if notify else None,
    )