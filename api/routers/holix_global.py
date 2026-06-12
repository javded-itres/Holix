"""Holix management: global config and env (admin only)."""

from __future__ import annotations

import yaml
from core.global_config import (
    deep_merge_dict,
    ensure_global_config,
    ensure_global_env_template,
    global_config_path,
    load_global_config_raw,
    strip_profile_only_keys,
)
from fastapi import APIRouter, Depends, Header

from api import state
from api.deps import verify_api_key
from api.schemas.holix import ConfigPatchRequest, EnvPatchRequest
from api.services.config_mask import mask_config_dict
from api.services.env_mask import mask_env_map
from api.services.env_store import patch_global_env, read_global_env_map
from api.services.holix_deps import profile_access
from api.services.profile_access import require_admin_access

router = APIRouter(prefix="/api/holix/global", tags=["holix-global"])


def _admin_context(
    key_info: dict,
    x_holix_profile: str | None,
    x_holix_profile_key: str | None,
):
    ctx = profile_access(state.host_profile, key_info, x_holix_profile, x_holix_profile_key)
    require_admin_access(ctx)
    return ctx


@router.post("/init")
async def init_global(
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    _admin_context(key_info, x_holix_profile, x_holix_profile_key)
    cfg_path = ensure_global_config()
    env_path = ensure_global_env_template()
    return {"config_path": str(cfg_path), "env_path": str(env_path), "initialized": True}


@router.get("/config")
async def get_global_config(
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    _admin_context(key_info, x_holix_profile, x_holix_profile_key)
    ensure_global_config()
    from core.config_utils import resolve_env_refs

    raw = load_global_config_raw()
    resolved = resolve_env_refs(raw)
    return {"config": mask_config_dict(resolved)}


@router.patch("/config")
async def patch_global_config(
    body: ConfigPatchRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    _admin_context(key_info, x_holix_profile, x_holix_profile_key)
    ensure_global_config()
    current = load_global_config_raw()
    merged = deep_merge_dict(current, body.updates)
    stripped = strip_profile_only_keys(merged)
    with open(global_config_path(), "w", encoding="utf-8") as handle:
        yaml.dump(stripped, handle, default_flow_style=False, allow_unicode=True)
    return {"reload_required": True}


@router.get("/env")
async def get_global_env(
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    _admin_context(key_info, x_holix_profile, x_holix_profile_key)
    values = read_global_env_map()
    return {"variables": mask_env_map(values), "count": len(values)}


@router.patch("/env")
async def patch_global_env_route(
    body: EnvPatchRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    _admin_context(key_info, x_holix_profile, x_holix_profile_key)
    patch_global_env(body.variables)
    return {"updated": list(body.variables.keys()), "reload_required": True}