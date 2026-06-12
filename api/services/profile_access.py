"""Profile-scoped access control for /api/holix management routes."""

from __future__ import annotations

import os
from dataclasses import dataclass

from core.profile_keys import profile_has_access_key, verify_profile_access_key
from core.security.permissions import PermissionChecker
from fastapi import HTTPException


def resolve_admin_holix_profile() -> str:
    from integrations.telegram.admin import DEFAULT_ADMIN_PROFILE

    return (os.getenv("HOLIX_TELEGRAM_ADMIN_PROFILE") or DEFAULT_ADMIN_PROFILE).strip() or DEFAULT_ADMIN_PROFILE


@dataclass(frozen=True, slots=True)
class ProfileAccessContext:
    target_profile: str
    is_admin: bool
    is_owner: bool


def verify_profile_management(
    target_profile: str,
    *,
    api_key_info: dict,
    x_holix_profile: str | None,
    x_holix_profile_key: str | None,
) -> ProfileAccessContext:
    """Authorize management of ``target_profile``.

    Allowed when:
    - API key has ``admin`` permission, or
    - ``X-Holix-Profile-Key`` matches the admin profile master key, or
    - header profile matches target and key unlocks that profile.
    """
    target = target_profile.strip()
    header_profile = (x_holix_profile or "").strip()

    checker = PermissionChecker(api_key_info.get("permissions") or [])
    if checker.is_admin():
        return ProfileAccessContext(target_profile=target, is_admin=True, is_owner=False)

    key = (x_holix_profile_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=401,
            detail="X-Holix-Profile-Key required for profile management",
        )

    admin_profile = resolve_admin_holix_profile()
    if verify_profile_access_key(admin_profile, key):
        return ProfileAccessContext(target_profile=target, is_admin=True, is_owner=False)

    if header_profile and header_profile != target:
        raise HTTPException(
            status_code=403,
            detail="X-Holix-Profile must match the target profile for non-admin access",
        )

    if not profile_has_access_key(target):
        return ProfileAccessContext(target_profile=target, is_admin=False, is_owner=True)

    if verify_profile_access_key(target, key):
        return ProfileAccessContext(target_profile=target, is_admin=False, is_owner=True)

    raise HTTPException(status_code=403, detail="Invalid profile access key")


def require_admin_access(ctx: ProfileAccessContext) -> None:
    if not ctx.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")