"""Approve or reject MAX access requests (CLI and bot callbacks)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from cli.core import (
    ProfileManager,
    enable_profile_workspace_isolation,
    validate_profile_name_for_env,
)
from core.profile_keys import profile_has_access_key, store_profile_access_key

from integrations.max.access_requests import (
    STATUS_PENDING,
    MaxAccessRequest,
    get_access_request,
    reject_access_request,
    resolve_access_request,
)
from integrations.max.admin import (
    load_admin_holix_profile,
    load_admin_user_id,
    set_admin_user,
)
from integrations.max.allowlist import add_allowed_user
from integrations.max.env_store import load_max_env_files
from integrations.max.user_profiles import set_user_profile


@dataclass(frozen=True, slots=True)
class AccessApprovalResult:
    ok: bool
    message: str
    holix_profile: str | None = None
    access_key: str | None = None
    user_display: str | None = None


def suggest_holix_profile_name(req: MaxAccessRequest) -> str:
    if req.username:
        slug = re.sub(r"[^a-z0-9_-]", "", req.username.lower())
        if len(slug) >= 2:
            return slug[:32]
    first = (req.first_name or "").strip().lower()
    if first:
        slug = re.sub(r"[^a-z0-9_-]", "", first.replace(" ", "-"))
        if len(slug) >= 2:
            return slug[:32]
    return f"user_{req.user_id}"


def _prepare_profile_for_user(
    manager: ProfileManager,
    target_profile: str,
    *,
    create_new: bool,
    bot_profile: str | None = None,
) -> tuple[str | None, bool]:
    target_profile = validate_profile_name_for_env(target_profile)
    access_key: str | None = None
    key_already_set = False

    if create_new:
        if manager.profile_exists(target_profile):
            if profile_has_access_key(target_profile):
                key_already_set = True
            else:
                access_key = store_profile_access_key(target_profile)
                enable_profile_workspace_isolation(manager, target_profile)
        else:
            manager.create_profile(target_profile, with_access_key=True)
            access_key = manager.pop_last_created_access_key()
        if bot_profile:
            from integrations.max.profile_seed import seed_max_user_profile_from_bot

            seed_max_user_profile_from_bot(
                manager,
                bot_profile=bot_profile,
                user_profile=target_profile,
            )
        return access_key, key_already_set

    if not manager.profile_exists(target_profile):
        raise ValueError(f"Profile '{target_profile}' not found")
    if bot_profile:
        from integrations.max.profile_seed import seed_max_user_profile_from_bot

        seed_max_user_profile_from_bot(
            manager,
            bot_profile=bot_profile,
            user_profile=target_profile,
        )
    return None, profile_has_access_key(target_profile)


def approve_access_request(
    bot_profile: str,
    user_id: int,
    *,
    holix_profile: str | None = None,
    create_profile: str | None = None,
    set_admin: bool = False,
) -> AccessApprovalResult:
    if set_admin and (holix_profile or create_profile):
        raise ValueError("set_admin cannot be combined with holix_profile or create_profile")

    load_max_env_files(bot_profile)
    req = get_access_request(bot_profile, user_id)
    if req is None or req.status != STATUS_PENDING:
        raise ValueError(f"No pending request for user id {user_id}")

    if set_admin:
        existing_admin = load_admin_user_id(bot_profile)
        if existing_admin is not None and int(existing_admin) != int(user_id):
            raise ValueError(f"Admin already assigned (user id {existing_admin})")

    target_profile: str | None = None
    if set_admin:
        target_profile = load_admin_holix_profile(bot_profile)
    elif create_profile:
        target_profile = create_profile.strip()
    elif holix_profile:
        target_profile = holix_profile.strip()

    manager = ProfileManager()
    if not target_profile:
        suggested = suggest_holix_profile_name(req)
        target_profile = suggested
        create_profile = suggested

    if set_admin and not manager.profile_exists(target_profile):
        manager.create_profile(target_profile, inherit_global=True)

    if set_admin:
        from core.profile_admin_seed import copy_profile_settings_from_source

        if manager.profile_exists("default"):
            copy_profile_settings_from_source(
                manager,
                source_profile="default",
                target_profile=target_profile,
            )

    access_key, key_already_set = _prepare_profile_for_user(
        manager,
        target_profile,
        create_new=bool(create_profile) and not set_admin,
        bot_profile=bot_profile,
    )

    if set_admin:
        set_admin_user(bot_profile, user_id, holix_profile=target_profile)

    add_allowed_user(bot_profile, user_id)
    set_user_profile(bot_profile, user_id, target_profile)
    resolve_access_request(
        bot_profile,
        user_id,
        status="approved",
        holix_profile=target_profile,
    )

    message = f"Доступ одобрен: {req.display_name} → профиль «{target_profile}»"
    if access_key:
        message += ". Ключ доступа создан (отправка в MAX — в следующих фазах)."

    return AccessApprovalResult(
        ok=True,
        message=message,
        holix_profile=target_profile,
        access_key=access_key,
        user_display=req.display_name,
    )


def reject_access_request_op(bot_profile: str, user_id: int) -> AccessApprovalResult:
    load_max_env_files(bot_profile)
    req = reject_access_request(bot_profile, user_id)
    if req is None:
        raise ValueError(f"No pending request for user id {user_id}")

    return AccessApprovalResult(
        ok=True,
        message=f"Запрос отклонён: {req.display_name}",
        user_display=req.display_name,
    )