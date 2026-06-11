"""Helix management: per-profile config and env."""

from __future__ import annotations

from cli.core import ProfileManager
from core.env_loader import read_profile_env_map
from core.global_config import deep_merge_dict
from fastapi import APIRouter, Depends, Header, HTTPException

from api.deps import verify_api_key
from api.schemas.helix import ConfigPatchRequest, EnvPatchRequest
from api.services.config_mask import mask_config_dict
from api.services.env_mask import mask_env_map
from api.services.env_store import patch_profile_env
from api.services.helix_deps import profile_access

router = APIRouter(prefix="/api/helix/profiles/{profile_id}", tags=["helix-config"])


def _require_profile(profile_id: str) -> tuple[ProfileManager, object]:
    manager = ProfileManager()
    if not manager.profile_exists(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    return manager, manager.load_profile(profile_id)


@router.get("/config")
async def get_config(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_helix_profile_key: str | None = Header(None, alias="X-Helix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_helix_profile, x_helix_profile_key)
    _, config = _require_profile(profile_id)
    payload = mask_config_dict(config.model_dump())
    return {"profile": profile_id, "config": payload}


@router.patch("/config")
async def patch_config(
    profile_id: str,
    body: ConfigPatchRequest,
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_helix_profile_key: str | None = Header(None, alias="X-Helix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_helix_profile, x_helix_profile_key)
    manager, config = _require_profile(profile_id)
    current = config.model_dump()
    merged = deep_merge_dict(current, body.updates)
    from cli.core import ProfileConfig

    updated = ProfileConfig(**merged)
    manager.save_profile(profile_id, updated)
    return {"profile": profile_id, "reload_required": True}


@router.get("/env")
async def get_env(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_helix_profile_key: str | None = Header(None, alias="X-Helix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_helix_profile, x_helix_profile_key)
    _require_profile(profile_id)
    values = read_profile_env_map(profile_id)
    return {"profile": profile_id, "variables": mask_env_map(values), "count": len(values)}


@router.patch("/env")
async def patch_env(
    profile_id: str,
    body: EnvPatchRequest,
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_helix_profile_key: str | None = Header(None, alias="X-Helix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_helix_profile, x_helix_profile_key)
    _require_profile(profile_id)
    patch_profile_env(profile_id, body.variables)
    masked = mask_env_map(body.variables)
    return {"profile": profile_id, "updated": list(masked.keys()), "reload_required": True}