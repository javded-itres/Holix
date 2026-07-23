"""Holix management: MAX bot setup, access requests, admin, user map."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Header, HTTPException

from api.deps import verify_api_key
from api.di import (
    CompanionManager,
    HostProfileName,
    ProfileManager,
)
from api.schemas.holix import MaxApproveRequest, MaxMapSetRequest, MaxSetupRequest
from api.services.holix_deps import ensure_profile_exists, profile_access
from api.services.max_ops import (
    MaxOpError,
    approve_access_request,
    clear_max_admin,
    get_max_admin,
    get_max_status,
    list_access_requests,
    list_bot_users,
    list_user_map,
    reject_access_request_op,
    remove_bot_user,
    remove_user_map,
    set_user_map,
    setup_max,
    sync_max_menu,
)
from api.services.profile_access import require_admin_access

router = APIRouter(prefix="/api/holix/profiles/{profile_id}/max", tags=["holix-max"], route_class=DishkaRoute)



def _map_op_error(exc: MaxOpError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/status")
async def max_status(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    ensure_profile_exists(manager, profile_id)
    return get_max_status(profile_id)


@router.post("/setup")
async def max_setup(
    companions: FromDishka[CompanionManager],
    host_profile: FromDishka[HostProfileName],
    manager: FromDishka[ProfileManager],
    profile_id: str,
    body: MaxSetupRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    ensure_profile_exists(manager, profile_id)
    try:
        result = await setup_max(
            profile_id,
            body.access_token,
            also_project_env=body.also_project_env,
        )
    except MaxOpError as exc:
        raise _map_op_error(exc) from exc

    if profile_id == str(host_profile):
        from integrations.max.gateway_routes import reload_max_webhook

        result["companions"] = await reload_max_webhook(profile_id)
        result["reload_required"] = False
    return result


@router.get("/requests")
async def max_requests(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    ensure_profile_exists(manager, profile_id)
    requests = list_access_requests(profile_id)
    return {"requests": requests, "count": len(requests)}


@router.post("/requests/{user_id}/approve")
async def max_approve(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    user_id: int,
    body: MaxApproveRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    ctx = profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    require_admin_access(ctx)
    ensure_profile_exists(manager, profile_id)
    if body.profile and body.create_profile:
        raise HTTPException(status_code=400, detail="Specify only profile or create_profile, not both")
    try:
        return await approve_access_request(
            profile_id,
            user_id,
            holix_profile=body.profile,
            create_profile=body.create_profile,
            set_admin=body.set_admin,
        )
    except MaxOpError as exc:
        raise _map_op_error(exc) from exc


@router.post("/requests/{user_id}/reject")
async def max_reject(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    user_id: int,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    ctx = profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    require_admin_access(ctx)
    ensure_profile_exists(manager, profile_id)
    try:
        return reject_access_request_op(profile_id, user_id)
    except MaxOpError as exc:
        raise _map_op_error(exc) from exc


@router.get("/admin")
async def max_admin_get(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    ensure_profile_exists(manager, profile_id)
    return get_max_admin(profile_id)


@router.delete("/admin")
async def max_admin_clear(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    ctx = profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    require_admin_access(ctx)
    ensure_profile_exists(manager, profile_id)
    try:
        return clear_max_admin(profile_id)
    except MaxOpError as exc:
        raise _map_op_error(exc) from exc


@router.get("/map")
async def max_map_list(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    ensure_profile_exists(manager, profile_id)
    return list_user_map(profile_id)


@router.post("/map")
async def max_map_set(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    body: MaxMapSetRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    ensure_profile_exists(manager, profile_id)
    return set_user_map(profile_id, body.user_id, body.profile)


@router.get("/users")
async def max_users_list(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    ensure_profile_exists(manager, profile_id)
    return list_bot_users(profile_id)


@router.delete("/users/{user_id}")
async def max_users_remove(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    user_id: int,
    notify: bool = True,
    force_admin: bool = False,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    ensure_profile_exists(manager, profile_id)
    try:
        return remove_bot_user(
            profile_id,
            user_id,
            notify=notify,
            force_admin=force_admin,
        )
    except MaxOpError as exc:
        raise _map_op_error(exc) from exc


@router.delete("/map/{user_id}")
async def max_map_remove(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    user_id: int,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    ensure_profile_exists(manager, profile_id)
    try:
        return remove_user_map(profile_id, user_id)
    except MaxOpError as exc:
        raise _map_op_error(exc) from exc


@router.post("/sync-menu")
async def max_sync_menu_route(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    ensure_profile_exists(manager, profile_id)
    try:
        return await sync_max_menu(profile_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc