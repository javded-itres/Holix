"""Shared FastAPI dependencies for /api/holix management routes."""

from __future__ import annotations

from fastapi import Depends, Header

from api.deps import verify_api_key
from api.services.profile_access import ProfileAccessContext, verify_profile_management


def profile_access(
    profile_id: str,
    key_info: dict,
    x_holix_profile: str | None,
    x_holix_profile_key: str | None,
) -> ProfileAccessContext:
    return verify_profile_management(
        profile_id,
        api_key_info=key_info,
        x_holix_profile=x_holix_profile,
        x_holix_profile_key=x_holix_profile_key,
    )


async def require_profile_access(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
) -> ProfileAccessContext:
    return profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)