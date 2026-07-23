"""Holix management: per-profile config and env."""

from __future__ import annotations

from core.env_loader import read_profile_env_map
from core.global_config import deep_merge_dict
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Header, HTTPException

from api.deps import verify_api_key
from api.schemas.holix import ConfigPatchRequest, EnvPatchRequest
from api.services.config_mask import mask_config_dict
from api.services.env_mask import mask_env_map
from api.services.env_store import patch_profile_env
from api.di import ProfileManager
from api.services.holix_deps import load_existing_profile, profile_access

router = APIRouter(prefix="/api/holix/profiles/{profile_id}", tags=["holix-config"], route_class=DishkaRoute)



@router.get("/config")
async def get_config(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _, config = load_existing_profile(manager, profile_id)
    payload = mask_config_dict(config.model_dump())
    return {"profile": profile_id, "config": payload}


@router.patch("/config")
async def patch_config(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    body: ConfigPatchRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager, config = load_existing_profile(manager, profile_id)
    current = config.model_dump()
    merged = deep_merge_dict(current, body.updates)
    from cli.core import ProfileConfig

    updated = ProfileConfig(**merged)
    manager.save_profile(profile_id, updated)
    return {"profile": profile_id, "reload_required": True}


@router.get("/env")
async def get_env(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    load_existing_profile(manager, profile_id)
    values = read_profile_env_map(profile_id)
    return {"profile": profile_id, "variables": mask_env_map(values), "count": len(values)}


@router.patch("/env")
async def patch_env(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    body: EnvPatchRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    load_existing_profile(manager, profile_id)
    patch_profile_env(profile_id, body.variables)
    masked = mask_env_map(body.variables)
    return {"profile": profile_id, "updated": list(masked.keys()), "reload_required": True}