"""Holix management: profiles CRUD, keys, jail, reload."""

from __future__ import annotations

from cli.core import ProfileManager, enable_profile_workspace_isolation
from core.profile_keys import (
    ProfileExistsError,
    profile_has_access_key,
    remove_profile_access_key,
    store_profile_access_key,
    verify_profile_access_key,
)
from fastapi import APIRouter, Depends, Header, HTTPException

from api import state
from api.deps import verify_api_key

from api.schemas.holix import (
    JailEnableRequest,
    ProfileCreateRequest,
    ProfileKeyRotateRequest,
    ReloadResponse,
)
from api.services.holix_deps import profile_access
from api.services.profile_access import require_admin_access

router = APIRouter(prefix="/api/holix/profiles", tags=["holix-profiles"])


@router.get("")
async def list_profiles(
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    ctx = profile_access(state.host_profile, key_info, x_holix_profile, x_holix_profile_key)
    require_admin_access(ctx)
    manager = ProfileManager()
    profiles = []
    for name in manager.list_profiles():
        profiles.append({
            "name": name,
            "protected": profile_has_access_key(name),
            "path": str(manager.get_profile_dir(name)),
        })
    return {"profiles": profiles, "count": len(profiles)}


@router.post("")
async def create_profile(
    body: ProfileCreateRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    ctx = profile_access(state.host_profile, key_info, x_holix_profile, x_holix_profile_key)
    require_admin_access(ctx)
    manager = ProfileManager()
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Profile name is required")
    try:
        with_key = body.with_access_key or body.workspace_jail
        manager.create_profile(
            name,
            with_access_key=with_key,
            inherit_global=body.inherit_global,
        )
    except ProfileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    access_key = manager.pop_last_created_access_key()
    if body.workspace_jail and not with_key:
        enable_profile_workspace_isolation(manager, name)

    return {
        "profile": name,
        "access_key": access_key,
        "protected": profile_has_access_key(name),
        "reload_required": False,
    }


@router.get("/{profile_id}")
async def get_profile(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager = ProfileManager()
    if not manager.profile_exists(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    config = manager.load_profile(profile_id)
    return {
        "profile": profile_id,
        "protected": profile_has_access_key(profile_id),
        "workspace_jail_enabled": config.workspace_jail_enabled,
        "workspace_root": config.workspace_root,
        "path": str(manager.get_profile_dir(profile_id)),
    }


@router.get("/{profile_id}/status")
async def profile_status(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager = ProfileManager()
    if not manager.profile_exists(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    loaded = profile_id in (state.registry.list_loaded_profiles() if state.registry else [])
    companions = state.companions.status(profile_id) if state.companions else {}
    return {
        "profile": profile_id,
        "exists": True,
        "protected": profile_has_access_key(profile_id),
        "agent_loaded": loaded,
        "companions": companions,
    }


@router.delete("/{profile_id}")
async def delete_profile(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
    notify: bool = True,
):
    ctx = profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    require_admin_access(ctx)
    from core.profile.lifecycle import PROTECTED_PROFILES, delete_profile_with_notification

    if profile_id in PROTECTED_PROFILES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete protected profile '{profile_id}'",
        )
    manager = ProfileManager()
    if not manager.profile_exists(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    if state.registry and profile_id in state.registry.list_loaded_profiles():
        entry = state.registry.entry(profile_id)
        if entry is not None:
            await state.registry.unload(profile_id)
    if state.companions:
        await state.companions.stop_cron(profile_id)
        await state.companions.stop_telegram(profile_id)
    result = delete_profile_with_notification(profile_id, notify=notify, manager=manager)
    from config import settings

    if result.error:
        detail = str(result.error) if settings.log_debug_enabled else "Profile deletion failed"
        raise HTTPException(status_code=400, detail=detail)
    if settings.log_debug_enabled:
        notify_failed = [
            {"user_id": uid, "error": str(err)} for uid, err in result.notify_failed
        ]
    else:
        notify_failed = [
            {"user_id": uid, "error": "Notification failed"}
            for uid, err in result.notify_failed
        ]
    return {
        "deleted": result.deleted,
        "profile": profile_id,
        "notified_users": result.notified,
        "notify_failed": notify_failed,
        "mappings_removed": result.mappings_removed,
    }


@router.post("/{profile_id}/reload", response_model=ReloadResponse)
async def reload_profile(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    if state.registry is None or state.companions is None:
        raise HTTPException(status_code=503, detail="Gateway not initialized")
    manager = ProfileManager()
    if not manager.profile_exists(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")

    from core.env_loader import bootstrap_profile_env

    bootstrap_profile_env(profile_id, force=True)

    await state.companions.stop_cron(profile_id)
    await state.companions.stop_telegram(profile_id)
    await state.companions.stop_max(profile_id)
    agent_result = await state.registry.reload(profile_id)
    companion_result = await state.companions.reload(profile_id)

    from cli.services.gateway_companions import reload_os_companions

    os_companion_result = reload_os_companions(profile_id)

    companion_result = dict(companion_result)
    import api.state as api_state

    if profile_id == api_state.host_profile:
        from integrations.max.gateway_routes import reload_max_webhook

        companion_result.update(await reload_max_webhook(profile_id))

    return ReloadResponse(
        profile=profile_id,
        status="reloaded",
        agent=agent_result.get("status", "reloaded"),
        companions=companion_result,
        os_companions=os_companion_result,
        reload_required=False,
    )


@router.get("/{profile_id}/key/status")
async def key_status(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    return {"profile": profile_id, "protected": profile_has_access_key(profile_id)}


@router.post("/{profile_id}/key/init")
async def key_init(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager = ProfileManager()
    if not manager.profile_exists(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile_has_access_key(profile_id):
        raise HTTPException(status_code=409, detail="Profile already protected")
    access_key = store_profile_access_key(profile_id)
    workspace = enable_profile_workspace_isolation(manager, profile_id)
    return {
        "profile": profile_id,
        "access_key": access_key,
        "workspace_root": str(workspace),
        "reload_required": True,
    }


@router.post("/{profile_id}/key/rotate")
async def key_rotate(
    profile_id: str,
    body: ProfileKeyRotateRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    if not profile_has_access_key(profile_id):
        raise HTTPException(status_code=400, detail="Profile has no access key")
    if not verify_profile_access_key(profile_id, body.current_key):
        raise HTTPException(status_code=403, detail="Current access key is invalid")
    access_key = store_profile_access_key(profile_id)
    return {"profile": profile_id, "access_key": access_key}


@router.post("/{profile_id}/key/disable")
async def key_disable(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    ctx = profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    require_admin_access(ctx)
    if not remove_profile_access_key(profile_id):
        raise HTTPException(status_code=400, detail="Profile has no access key")
    return {"profile": profile_id, "protected": False}


@router.get("/{profile_id}/jail")
async def jail_status(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    config = ProfileManager().load_profile(profile_id)
    return {
        "enabled": config.workspace_jail_enabled,
        "workspace_root": config.workspace_root,
    }


@router.post("/{profile_id}/jail/enable")
async def jail_enable(
    profile_id: str,
    body: JailEnableRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager = ProfileManager()
    config = manager.load_profile(profile_id)
    if body.path:
        from pathlib import Path

        from core.profile.names import ensure_profile_workspace_dir

        workspace = ensure_profile_workspace_dir(profile_id, Path(body.path))
        config.workspace_root = str(workspace)
    else:
        workspace = enable_profile_workspace_isolation(manager, profile_id)
        config.workspace_root = str(workspace)
    config.workspace_jail_enabled = True
    manager.save_profile(profile_id, config)
    return {
        "enabled": True,
        "workspace_root": config.workspace_root,
        "reload_required": True,
    }


@router.post("/{profile_id}/jail/disable")
async def jail_disable(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager = ProfileManager()
    config = manager.load_profile(profile_id)
    config.workspace_jail_enabled = False
    manager.save_profile(profile_id, config)
    return {"enabled": False, "reload_required": True}