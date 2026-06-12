"""Thin wrappers over Telegram CLI/integration logic for gateway API."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from integrations.telegram.access_approval import (
    approve_access_request as approve_access_request_core,
)
from integrations.telegram.access_approval import (
    reject_access_request_op as reject_access_request_core,
)
from integrations.telegram.access_requests import (
    TelegramAccessRequest,
    list_pending_requests,
    register_access_request,
)
from integrations.telegram.admin import (
    clear_admin_user,
    load_admin_holix_profile,
    load_admin_user_id,
)
from integrations.telegram.env_store import (
    load_telegram_env_files,
    mask_token,
    read_telegram_env_values,
    save_telegram_env,
    telegram_env_path,
    token_looks_valid,
)
from integrations.telegram.setup_api import TelegramApiError, verify_bot_token
from integrations.telegram.user_profiles import (
    load_user_profiles,
    remove_user_profile,
    set_user_profile,
    telegram_users_path,
)


class TelegramOpError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _request_dict(req: TelegramAccessRequest) -> dict[str, Any]:
    data = asdict(req)
    data["display_name"] = req.display_name
    return data


def get_telegram_status(profile_id: str) -> dict[str, Any]:
    from integrations.telegram.config import load_telegram_settings

    from api import state

    load_telegram_env_files(profile_id)
    settings = load_telegram_settings(profile_id)
    admin_id = load_admin_user_id(profile_id)
    mapping = load_user_profiles(profile_id)
    pending = list_pending_requests(profile_id)
    companions = state.companions.status(profile_id) if state.companions else {}

    return {
        "profile": profile_id,
        "configured": bool(settings.bot_token.strip()),
        "token_masked": mask_token(settings.bot_token),
        "access_requests_enabled": settings.access_requests,
        "pending_count": len(pending),
        "allowed_user_ids": settings.allowed_user_ids,
        "admin_user_id": admin_id,
        "admin_holix_profile": load_admin_holix_profile(profile_id) if admin_id else None,
        "user_profile_map": {str(uid): name for uid, name in sorted(mapping.items())},
        "telegram_env_path": str(telegram_env_path(profile_id)),
        "user_profiles_path": str(telegram_users_path(profile_id)),
        "companions": companions,
    }


async def setup_telegram(
    profile_id: str,
    bot_token: str,
    *,
    also_project_env: bool = False,
) -> dict[str, Any]:
    token = bot_token.strip()
    if not token_looks_valid(token):
        raise TelegramOpError("Invalid bot token format")

    try:
        me = await verify_bot_token(token)
    except TelegramApiError as exc:
        raise TelegramOpError(str(exc), status_code=400) from exc

    load_telegram_env_files(profile_id)
    existing = read_telegram_env_values(profile_id)
    values = {
        "TELEGRAM_BOT_TOKEN": token,
        "HOLIX_TELEGRAM_ACCESS_REQUESTS": "true",
    }
    allowed = existing.get("HOLIX_TELEGRAM_ALLOWED_USERS", "").strip()
    if allowed:
        values["HOLIX_TELEGRAM_ALLOWED_USERS"] = allowed.replace(" ", "")
    edit_ms = existing.get("HOLIX_TELEGRAM_EDIT_MS", "")
    if edit_ms:
        values["HOLIX_TELEGRAM_EDIT_MS"] = edit_ms

    path = save_telegram_env(values, profile=profile_id)
    if also_project_env:
        from pathlib import Path

        from integrations.telegram.env_store import merge_project_env

        merge_project_env(Path.cwd() / ".env", values)

    username = me.get("username") or me.get("first_name") or "bot"
    return {
        "profile": profile_id,
        "bot_id": me.get("id"),
        "bot_username": username,
        "token_masked": mask_token(token),
        "config_path": str(path),
        "reload_required": True,
    }


def list_access_requests(profile_id: str) -> list[dict[str, Any]]:
    load_telegram_env_files(profile_id)
    return [_request_dict(req) for req in list_pending_requests(profile_id)]


async def approve_access_request(
    profile_id: str,
    user_id: int,
    *,
    holix_profile: str | None = None,
    create_profile: str | None = None,
    set_admin: bool = False,
) -> dict[str, Any]:
    if set_admin and (holix_profile or create_profile):
        raise TelegramOpError("--set-admin cannot be combined with profile or create_profile")
    if not set_admin and not holix_profile and not create_profile:
        raise TelegramOpError("profile or create_profile is required")

    try:
        result = approve_access_request_core(
            profile_id,
            user_id,
            holix_profile=holix_profile,
            create_profile=create_profile,
            set_admin=set_admin,
        )
    except ValueError as exc:
        msg = str(exc)
        status = 409 if "Admin already" in msg else 404
        raise TelegramOpError(msg, status_code=status) from exc

    payload: dict[str, Any] = {
        "user_id": user_id,
        "holix_profile": result.holix_profile,
        "set_admin": set_admin,
        "reload_required": True,
    }
    if result.access_key:
        payload["access_key"] = result.access_key
    return payload


def reject_access_request_op(profile_id: str, user_id: int) -> dict[str, Any]:
    try:
        result = reject_access_request_core(profile_id, user_id)
    except ValueError as exc:
        raise TelegramOpError(str(exc), status_code=404) from exc
    return {
        "user_id": user_id,
        "status": "rejected",
        "display_name": result.user_display,
    }


def get_telegram_admin(profile_id: str) -> dict[str, Any]:
    load_telegram_env_files(profile_id)
    admin_id = load_admin_user_id(profile_id)
    if admin_id is None:
        return {"assigned": False, "user_id": None, "holix_profile": None}
    return {
        "assigned": True,
        "user_id": admin_id,
        "holix_profile": load_admin_holix_profile(profile_id),
    }


def clear_telegram_admin(profile_id: str) -> dict[str, Any]:
    load_telegram_env_files(profile_id)
    if load_admin_user_id(profile_id) is None:
        return {"cleared": False}
    if not clear_admin_user(profile_id):
        raise TelegramOpError("Failed to clear admin", status_code=500)
    return {"cleared": True, "reload_required": True}


def list_user_map(profile_id: str) -> dict[str, Any]:
    load_telegram_env_files(profile_id)
    mapping = load_user_profiles(profile_id)
    return {
        "map": {str(uid): name for uid, name in sorted(mapping.items())},
        "path": str(telegram_users_path(profile_id)),
        "count": len(mapping),
    }


def set_user_map(profile_id: str, user_id: int, holix_profile: str) -> dict[str, Any]:
    load_telegram_env_files(profile_id)
    path = set_user_profile(profile_id, user_id, holix_profile.strip())
    return {
        "user_id": user_id,
        "holix_profile": holix_profile.strip(),
        "path": str(path),
        "reload_required": True,
    }


def remove_user_map(profile_id: str, user_id: int) -> dict[str, Any]:
    load_telegram_env_files(profile_id)
    path = remove_user_profile(profile_id, user_id)
    if path is None:
        raise TelegramOpError(f"No mapping for user id {user_id}", status_code=404)
    return {"user_id": user_id, "removed": True, "reload_required": True}


async def sync_telegram_menu(profile_id: str) -> dict[str, Any]:
    from integrations.telegram.commands import sync_bot_menu

    load_telegram_env_files(profile_id)
    names = await sync_bot_menu(profile_id)
    return {"commands": names, "count": len(names)}


def seed_pending_request_for_tests(
    profile_id: str,
    user_id: int,
    *,
    username: str | None = "tester",
    first_name: str = "Test",
) -> TelegramAccessRequest:
    """Helper used by tests to register a pending access request."""
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"}, profile=profile_id)
    req, _ = register_access_request(
        profile_id,
        user_id=user_id,
        username=username,
        first_name=first_name,
    )
    return req