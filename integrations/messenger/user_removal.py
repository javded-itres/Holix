"""Remove a messenger user from allowlist, profile map, and access requests."""

from __future__ import annotations

from dataclasses import dataclass

from integrations.messenger.access_requests import (
    delete_access_request,
    get_access_request,
    load_access_requests,
)
from integrations.messenger.admin import clear_admin_user, load_admin_user_id
from integrations.messenger.allowlist import load_allowed_user_ids, remove_allowed_user
from integrations.messenger.env_store import load_messenger_env_files
from integrations.messenger.platform import MessengerPlatform
from integrations.messenger.user_profiles import load_user_profiles, remove_user_profile


@dataclass(frozen=True, slots=True)
class MessengerUserRemovalResult:
    ok: bool
    user_id: int
    message: str
    holix_profile: str | None = None
    removed_allowlist: bool = False
    removed_mapping: bool = False
    removed_access_request: bool = False
    cleared_admin: bool = False
    notified: bool = False
    notify_error: str | None = None


def list_known_user_ids(platform: MessengerPlatform, bot_profile: str) -> dict[int, dict[str, str]]:
    """Summarize every user id referenced in allowlist, map, or access requests."""
    load_messenger_env_files(platform, bot_profile)
    out: dict[int, dict[str, str]] = {}

    def _ensure(uid: int) -> dict[str, str]:
        return out.setdefault(int(uid), {})

    for uid in load_allowed_user_ids(platform, bot_profile):
        entry = _ensure(uid)
        entry["allowlist"] = "yes"

    for uid, profile in load_user_profiles(platform, bot_profile).items():
        entry = _ensure(uid)
        entry["profile"] = profile

    admin_id = load_admin_user_id(platform, bot_profile)
    if admin_id is not None:
        entry = _ensure(int(admin_id))
        entry["admin"] = "yes"

    for req in load_access_requests(platform, bot_profile).values():
        entry = _ensure(req.user_id)
        entry["request_status"] = req.status
        if req.holix_profile:
            entry.setdefault("profile", req.holix_profile)

    return out


def remove_messenger_user(
    platform: MessengerPlatform,
    bot_profile: str,
    user_id: int,
    *,
    notify: bool = True,
    force_admin: bool = False,
    notify_revoked_sync: object | None = None,
) -> MessengerUserRemovalResult:
    """Fully revoke messenger access for *user_id*."""
    load_messenger_env_files(platform, bot_profile)
    uid = int(user_id)

    admin_id = load_admin_user_id(platform, bot_profile)
    is_admin = admin_id is not None and int(admin_id) == uid

    if is_admin and not force_admin:
        raise ValueError(
            f"User id {uid} is the bot administrator. "
            "Clear admin first or pass force_admin=True."
        )

    mapping = load_user_profiles(platform, bot_profile)
    holix_profile = mapping.get(uid)
    in_allowlist = uid in load_allowed_user_ids(platform, bot_profile)
    had_request = get_access_request(platform, bot_profile, uid) is not None
    had_mapping = uid in mapping

    if not (in_allowlist or had_mapping or had_request or is_admin):
        raise ValueError(f"No data for user id {uid}")

    cleared_admin = False
    if is_admin and force_admin:
        cleared_admin = clear_admin_user(platform, bot_profile)

    removed_allowlist = remove_allowed_user(platform, bot_profile, uid) is not None
    removed_mapping = remove_user_profile(platform, bot_profile, uid) is not None
    removed_access_request = delete_access_request(platform, bot_profile, uid)

    had_access = in_allowlist or had_mapping
    notified = False
    notify_error: str | None = None
    if notify and had_access and notify_revoked_sync is not None:
        try:
            notify_revoked_sync(bot_profile, uid)
            notified = True
        except Exception as exc:
            notify_error = str(exc)

    parts: list[str] = [f"Пользователь {uid} удалён"]
    if holix_profile:
        parts.append(f"профиль «{holix_profile}»")
    if cleared_admin:
        parts.append("снят статус администратора")
    message = ": ".join(parts[:1]) + (
        " (" + ", ".join(parts[1:]) + ")" if len(parts) > 1 else ""
    )
    if notify_error:
        message += f" (уведомление: {notify_error})"

    return MessengerUserRemovalResult(
        ok=True,
        user_id=uid,
        message=message,
        holix_profile=holix_profile,
        removed_allowlist=removed_allowlist,
        removed_mapping=removed_mapping,
        removed_access_request=removed_access_request,
        cleared_admin=cleared_admin,
        notified=notified,
        notify_error=notify_error,
    )