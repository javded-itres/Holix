"""Holix management: Telegram bot setup, access requests, admin, user map."""

from __future__ import annotations

from cli.core import ProfileManager
from fastapi import APIRouter, Depends, Header, HTTPException

from api import state
from api.deps import verify_api_key
from api.schemas.holix import TelegramApproveRequest, TelegramMapSetRequest, TelegramSetupRequest
from api.services.holix_deps import profile_access
from api.services.profile_access import require_admin_access
from api.services.telegram_ops import (
    TelegramOpError,
    approve_access_request,
    clear_telegram_admin,
    get_telegram_admin,
    get_telegram_status,
    list_access_requests,
    list_user_map,
    reject_access_request_op,
    remove_user_map,
    set_user_map,
    setup_telegram,
    sync_telegram_menu,
)

router = APIRouter(prefix="/api/holix/profiles/{profile_id}/telegram", tags=["holix-telegram"])


def _require_profile(profile_id: str) -> None:
    if not ProfileManager().profile_exists(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")


def _map_op_error(exc: TelegramOpError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/status")
async def telegram_status(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    return get_telegram_status(profile_id)


@router.post("/setup")
async def telegram_setup(
    profile_id: str,
    body: TelegramSetupRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    try:
        result = await setup_telegram(
            profile_id,
            body.bot_token,
            also_project_env=body.also_project_env,
        )
    except TelegramOpError as exc:
        raise _map_op_error(exc) from exc

    if state.companions is not None:
        await state.companions.reload(profile_id)
        result["reload_required"] = False
        result["companions"] = state.companions.status(profile_id)
    return result


@router.get("/requests")
async def telegram_requests(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    requests = list_access_requests(profile_id)
    return {"requests": requests, "count": len(requests)}


@router.post("/requests/{user_id}/approve")
async def telegram_approve(
    profile_id: str,
    user_id: int,
    body: TelegramApproveRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    ctx = profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    require_admin_access(ctx)
    _require_profile(profile_id)
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
    except TelegramOpError as exc:
        raise _map_op_error(exc) from exc


@router.post("/requests/{user_id}/reject")
async def telegram_reject(
    profile_id: str,
    user_id: int,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    ctx = profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    require_admin_access(ctx)
    _require_profile(profile_id)
    try:
        return reject_access_request_op(profile_id, user_id)
    except TelegramOpError as exc:
        raise _map_op_error(exc) from exc


@router.get("/admin")
async def telegram_admin_get(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    return get_telegram_admin(profile_id)


@router.delete("/admin")
async def telegram_admin_clear(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    ctx = profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    require_admin_access(ctx)
    _require_profile(profile_id)
    try:
        return clear_telegram_admin(profile_id)
    except TelegramOpError as exc:
        raise _map_op_error(exc) from exc


@router.get("/map")
async def telegram_map_list(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    return list_user_map(profile_id)


@router.post("/map")
async def telegram_map_set(
    profile_id: str,
    body: TelegramMapSetRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    return set_user_map(profile_id, body.user_id, body.profile)


@router.delete("/map/{user_id}")
async def telegram_map_remove(
    profile_id: str,
    user_id: int,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    try:
        return remove_user_map(profile_id, user_id)
    except TelegramOpError as exc:
        raise _map_op_error(exc) from exc


@router.post("/sync-menu")
async def telegram_sync_menu(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    try:
        return await sync_telegram_menu(profile_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc