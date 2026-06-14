"""Thin wrappers over MAX CLI/integration logic for gateway API."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from integrations.max.access_approval import (
    approve_access_request as approve_access_request_core,
)
from integrations.max.access_approval import (
    reject_access_request_op as reject_access_request_core,
)
from integrations.max.access_requests import (
    MaxAccessRequest,
    list_pending_requests,
    register_access_request,
)
from integrations.max.admin import (
    clear_admin_user,
    load_admin_holix_profile,
    load_admin_user_id,
)
from integrations.max.env_store import (
    load_max_env_files,
    mask_token,
    max_env_path,
    read_max_env_values,
    save_max_env,
    token_looks_valid,
)
from integrations.max.setup_api import MaxApiError, verify_access_token
from integrations.max.user_profiles import (
    load_user_profiles,
    max_users_path,
    remove_user_profile,
    set_user_profile,
)
from integrations.max.user_removal import list_known_user_ids, remove_max_user


class MaxOpError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _request_dict(req: MaxAccessRequest) -> dict[str, Any]:
    data = asdict(req)
    data["display_name"] = req.display_name
    return data


def get_max_status(profile_id: str) -> dict[str, Any]:
    from integrations.max.config import load_max_settings


    load_max_env_files(profile_id)
    settings = load_max_settings(profile_id)
    admin_id = load_admin_user_id(profile_id)
    mapping = load_user_profiles(profile_id)
    pending = list_pending_requests(profile_id)

    return {
        "profile": profile_id,
        "configured": bool(settings.access_token.strip()),
        "token_masked": mask_token(settings.access_token),
        "access_requests_enabled": settings.access_requests,
        "pending_count": len(pending),
        "allowed_user_ids": settings.allowed_user_ids,
        "admin_user_id": admin_id,
        "admin_holix_profile": load_admin_holix_profile(profile_id) if admin_id else None,
        "user_profile_map": {str(uid): name for uid, name in sorted(mapping.items())},
        "max_env_path": str(max_env_path(profile_id)),
        "user_profiles_path": str(max_users_path(profile_id)),
        "max_webhook": True,
        "mode": settings.mode,
    }


async def setup_max(
    profile_id: str,
    access_token: str,
    *,
    also_project_env: bool = False,
) -> dict[str, Any]:
    token = access_token.strip()
    if not token_looks_valid(token):
        raise MaxOpError("Invalid access token format")

    try:
        me = await verify_access_token(token)
    except MaxApiError as exc:
        raise MaxOpError(str(exc), status_code=400) from exc

    load_max_env_files(profile_id)
    existing = read_max_env_values(profile_id)
    values: dict[str, str] = {
        "MAX_ACCESS_TOKEN": token,
        "HOLIX_MAX_ACCESS_REQUESTS": "true",
        "HOLIX_MAX_PROFILE": profile_id,
    }
    allowed = existing.get("HOLIX_MAX_ALLOWED_USERS", existing.get("HELIX_MAX_ALLOWED_USERS", "")).strip()
    if allowed:
        values["HOLIX_MAX_ALLOWED_USERS"] = allowed.replace(" ", "")
    mode = existing.get("HOLIX_MAX_MODE", existing.get("HELIX_MAX_MODE", "")).strip()
    if mode:
        values["HOLIX_MAX_MODE"] = mode

    path = save_max_env(values, profile=profile_id)
    if also_project_env:
        from pathlib import Path

        from integrations.max.env_store import merge_project_env

        merge_project_env(Path.cwd() / ".env", values)

    username = me.get("username") or me.get("name") or "bot"
    return {
        "profile": profile_id,
        "bot_user_id": me.get("user_id"),
        "bot_username": username,
        "token_masked": mask_token(token),
        "config_path": str(path),
        "reload_required": True,
    }


def list_access_requests(profile_id: str) -> list[dict[str, Any]]:
    load_max_env_files(profile_id)
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
        raise MaxOpError("--set-admin cannot be combined with profile or create_profile")
    if not set_admin and not holix_profile and not create_profile:
        raise MaxOpError("profile or create_profile is required")

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
        raise MaxOpError(msg, status_code=status) from exc

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
        raise MaxOpError(str(exc), status_code=404) from exc
    return {
        "user_id": user_id,
        "status": "rejected",
        "display_name": result.user_display,
    }


def get_max_admin(profile_id: str) -> dict[str, Any]:
    load_max_env_files(profile_id)
    admin_id = load_admin_user_id(profile_id)
    if admin_id is None:
        return {"assigned": False, "user_id": None, "holix_profile": None}
    return {
        "assigned": True,
        "user_id": admin_id,
        "holix_profile": load_admin_holix_profile(profile_id),
    }


def clear_max_admin(profile_id: str) -> dict[str, Any]:
    load_max_env_files(profile_id)
    if load_admin_user_id(profile_id) is None:
        return {"cleared": False}
    if not clear_admin_user(profile_id):
        raise MaxOpError("Failed to clear admin", status_code=500)
    return {"cleared": True, "reload_required": True}


def list_user_map(profile_id: str) -> dict[str, Any]:
    load_max_env_files(profile_id)
    mapping = load_user_profiles(profile_id)
    return {
        "map": {str(uid): name for uid, name in sorted(mapping.items())},
        "path": str(max_users_path(profile_id)),
        "count": len(mapping),
    }


def set_user_map(profile_id: str, user_id: int, holix_profile: str) -> dict[str, Any]:
    load_max_env_files(profile_id)
    path = set_user_profile(profile_id, user_id, holix_profile.strip())
    return {
        "user_id": user_id,
        "holix_profile": holix_profile.strip(),
        "path": str(path),
        "reload_required": True,
    }


def remove_user_map(profile_id: str, user_id: int) -> dict[str, Any]:
    load_max_env_files(profile_id)
    path = remove_user_profile(profile_id, user_id)
    if path is None:
        raise MaxOpError(f"No mapping for user id {user_id}", status_code=404)
    return {"user_id": user_id, "removed": True, "reload_required": True}


def list_bot_users(profile_id: str) -> dict[str, Any]:
    load_max_env_files(profile_id)
    users = list_known_user_ids(profile_id)
    return {
        "users": {str(uid): meta for uid, meta in sorted(users.items())},
        "count": len(users),
    }


def remove_bot_user(
    profile_id: str,
    user_id: int,
    *,
    notify: bool = True,
    force_admin: bool = False,
) -> dict[str, Any]:
    load_max_env_files(profile_id)
    try:
        result = remove_max_user(
            profile_id,
            user_id,
            notify=notify,
            force_admin=force_admin,
        )
    except ValueError as exc:
        msg = str(exc)
        status = 409 if "administrator" in msg.lower() else 404
        raise MaxOpError(msg, status_code=status) from exc
    return {
        "user_id": result.user_id,
        "removed": True,
        "holix_profile": result.holix_profile,
        "removed_allowlist": result.removed_allowlist,
        "removed_mapping": result.removed_mapping,
        "removed_access_request": result.removed_access_request,
        "cleared_admin": result.cleared_admin,
        "notified": result.notified,
        "notify_error": result.notify_error,
        "reload_required": True,
    }


async def sync_max_menu(profile_id: str) -> dict[str, Any]:
    from integrations.max.commands import sync_bot_menu

    load_max_env_files(profile_id)
    names = await sync_bot_menu(profile_id)
    return {"commands": names, "count": len(names)}


def seed_pending_request_for_tests(
    profile_id: str,
    user_id: int,
    *,
    username: str | None = "tester",
    first_name: str = "Test",
) -> MaxAccessRequest:
    save_max_env({"MAX_ACCESS_TOKEN": "a" * 32}, profile=profile_id)
    req, _ = register_access_request(
        profile_id,
        user_id=user_id,
        username=username,
        first_name=first_name,
    )
    return req