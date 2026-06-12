"""Approve or reject Telegram access requests (CLI, API, and bot callbacks)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from cli.core import (
    ProfileManager,
    enable_profile_workspace_isolation,
    validate_profile_name_for_env,
)
from core.profile_keys import profile_has_access_key, store_profile_access_key

from integrations.telegram.access_requests import (
    STATUS_PENDING,
    TelegramAccessRequest,
    get_access_request,
    reject_access_request,
    resolve_access_request,
)
from integrations.telegram.admin import (
    load_admin_holix_profile,
    load_admin_user_id,
    set_admin_user,
)
from integrations.telegram.allowlist import add_allowed_user
from integrations.telegram.env_store import load_telegram_env_files
from integrations.telegram.user_profiles import set_user_profile


@dataclass(frozen=True, slots=True)
class AccessApprovalResult:
    ok: bool
    message: str
    holix_profile: str | None = None
    access_key: str | None = None
    user_display: str | None = None


def is_telegram_admin(bot_profile: str, actor_user_id: int) -> bool:
    admin_id = load_admin_user_id(bot_profile)
    return admin_id is not None and int(admin_id) == int(actor_user_id)


def suggest_holix_profile_name(req: TelegramAccessRequest) -> str:
    """Derive a safe Holix profile name from Telegram user metadata."""
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
            from integrations.telegram.profile_seed import seed_telegram_user_profile_from_bot

            seed_telegram_user_profile_from_bot(
                manager,
                bot_profile=bot_profile,
                user_profile=target_profile,
            )
        return access_key, key_already_set

    if not manager.profile_exists(target_profile):
        raise ValueError(f"Profile '{target_profile}' not found")
    if bot_profile:
        from integrations.telegram.profile_seed import seed_telegram_user_profile_from_bot

        seed_telegram_user_profile_from_bot(
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
    """Grant Telegram user access and map to a Holix profile."""
    if set_admin and (holix_profile or create_profile):
        raise ValueError("set_admin cannot be combined with holix_profile or create_profile")

    load_telegram_env_files(bot_profile)
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
        if manager.profile_exists(suggested):
            target_profile = suggested
        else:
            target_profile = suggested
            create_profile = suggested
    if set_admin and not manager.profile_exists(target_profile):
        manager.create_profile(target_profile, inherit_global=True)

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

    notify_error: str | None = None
    try:
        from integrations.telegram.notify import notify_access_approved_sync

        notify_access_approved_sync(
            bot_profile,
            user_id,
            target_profile,
            access_key=access_key,
            key_already_set=key_already_set and not access_key,
        )
    except Exception as exc:
        notify_error = str(exc)

    message = (
        f"Доступ одобрен: {req.display_name} → профиль «{target_profile}»"
    )
    if access_key:
        message += ". Ключ отправлен пользователю в Telegram."
    if notify_error:
        message += f" (уведомление: {notify_error})"

    return AccessApprovalResult(
        ok=True,
        message=message,
        holix_profile=target_profile,
        access_key=access_key,
        user_display=req.display_name,
    )


def reject_access_request_op(bot_profile: str, user_id: int) -> AccessApprovalResult:
    load_telegram_env_files(bot_profile)
    req = reject_access_request(bot_profile, user_id)
    if req is None:
        raise ValueError(f"No pending request for user id {user_id}")

    notify_error: str | None = None
    try:
        from integrations.telegram.notify import notify_access_rejected_sync

        notify_access_rejected_sync(bot_profile, user_id)
    except Exception as exc:
        notify_error = str(exc)

    message = f"Запрос отклонён: {req.display_name}"
    if notify_error:
        message += f" ({notify_error})"
    return AccessApprovalResult(
        ok=True,
        message=message,
        user_display=req.display_name,
    )


def list_profiles_for_picker() -> list[str]:
    try:
        profiles = ProfileManager().list_profiles()
        return profiles or ["default"]
    except Exception:
        return ["default"]


async def handle_access_admin_callback(
    bot_profile: str,
    *,
    actor_user_id: int,
    action: str,
    value: str,
    message: Any | None = None,
    bot: Any | None = None,
) -> str:
    """Process admin inline buttons for access requests."""
    from integrations.telegram.keyboards import (
        access_request_profile_keyboard,
        format_access_resolved_admin_text,
    )

    if not is_telegram_admin(bot_profile, actor_user_id):
        return "Только администратор бота может одобрять доступ."

    if action == "ara":
        user_id = int(value)
        result = approve_access_request(bot_profile, user_id, create_profile=None)
        if message is not None and bot is not None:
            await message.edit_text(
                format_access_resolved_admin_text(result, approved=True),
                parse_mode="HTML",
            )
        return result.message

    if action == "arr":
        user_id = int(value)
        result = reject_access_request_op(bot_profile, user_id)
        if message is not None and bot is not None:
            await message.edit_text(
                format_access_resolved_admin_text(result, approved=False),
                parse_mode="HTML",
            )
        return result.message

    if action == "arb":
        user_id = int(value)
        req = get_access_request(bot_profile, user_id)
        if req is None:
            return "Запрос не найден."
        if message is not None and bot is not None:
            from integrations.telegram.keyboards import access_request_admin_keyboard
            from integrations.telegram.notify import format_access_request_admin_message

            await message.edit_text(
                format_access_request_admin_message(req, bot_profile),
                parse_mode="HTML",
                reply_markup=access_request_admin_keyboard(user_id),
            )
        return "Запрос доступа"

    if action == "arl":
        user_id = int(value)
        req = get_access_request(bot_profile, user_id)
        if req is None or req.status != STATUS_PENDING:
            return "Запрос уже обработан."
        profiles = list_profiles_for_picker()
        suggested = suggest_holix_profile_name(req)
        if message is not None and bot is not None:
            from integrations.telegram.notify import format_access_request_admin_message

            await message.edit_text(
                format_access_request_admin_message(req, bot_profile, pick_profile=True),
                parse_mode="HTML",
                reply_markup=access_request_profile_keyboard(
                    user_id,
                    profiles,
                    suggested=suggested,
                ),
            )
        return "Выберите профиль"

    if action == "arp":
        user_part, _, idx_part = value.partition(":")
        user_id = int(user_part)
        idx = int(idx_part)
        req = get_access_request(bot_profile, user_id)
        if req is None or req.status != STATUS_PENDING:
            return "Запрос уже обработан."
        profiles = list_profiles_for_picker()
        suggested = suggest_holix_profile_name(req)
        if idx == len(profiles):
            result = approve_access_request(
                bot_profile,
                user_id,
                create_profile=suggested,
            )
        elif 0 <= idx < len(profiles):
            result = approve_access_request(
                bot_profile,
                user_id,
                holix_profile=profiles[idx],
            )
        else:
            return "Неверный профиль"
        if message is not None and bot is not None:
            await message.edit_text(
                format_access_resolved_admin_text(result, approved=True),
                parse_mode="HTML",
            )
        return result.message

    return "Неизвестное действие"