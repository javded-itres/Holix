"""Holix management: external CLI launch (tmux) on Linux/macOS."""

from __future__ import annotations

from pathlib import Path

from cli.core import ProfileManager
from core.external_cli.launch_service import (
    LaunchServiceError,
    assign_cli,
    capture_session_output,
    kill_launch_session,
    launch_external_cli,
    list_clis,
    list_sessions,
    send_session_message,
    unassign_cli,
)
from core.external_cli.platform import launch_supported
from core.external_cli.registry import list_cli_specs
from fastapi import APIRouter, Depends, Header, HTTPException, Query

from api.deps import verify_api_key
from api.schemas.holix import (
    LaunchAssignRequest,
    LaunchCliRequest,
    LaunchSendRequest,
)
from api.services.holix_deps import profile_access

router = APIRouter(prefix="/api/holix/profiles/{profile_id}/launch", tags=["holix-launch"])


def _require_profile(profile_id: str) -> None:
    if not ProfileManager().profile_exists(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")


def _launch_http_error(exc: LaunchServiceError) -> HTTPException:
    text = str(exc).lower()
    if "not found" in text:
        return HTTPException(status_code=404, detail=str(exc))
    if "only on linux and macos" in text:
        return HTTPException(status_code=501, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/clis")
async def get_launch_clis(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    return {
        "supported": launch_supported(),
        "clis": list_clis(profile_id),
        "count": len(list_cli_specs()),
    }


@router.get("/sessions")
async def get_launch_sessions(
    profile_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    sessions = list_sessions(profile_id)
    return {"sessions": sessions, "count": len(sessions)}


@router.post("/{cli_id}")
async def post_launch_cli(
    profile_id: str,
    cli_id: str,
    body: LaunchCliRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    try:
        session = launch_external_cli(
            profile_id,
            cli_id,
            task=body.task,
            cwd=body.cwd,
            model_slot=body.model_slot,
            restart=body.restart,
        )
    except LaunchServiceError as exc:
        raise _launch_http_error(exc) from exc
    return {"session": session, "restart": body.restart}


@router.post("/{cli_id}/restart")
async def post_restart_cli(
    profile_id: str,
    cli_id: str,
    body: LaunchCliRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    try:
        session = launch_external_cli(
            profile_id,
            cli_id,
            task=body.task,
            cwd=body.cwd,
            model_slot=body.model_slot,
            restart=True,
        )
    except LaunchServiceError as exc:
        raise _launch_http_error(exc) from exc
    return {"session": session, "restart": True}


@router.patch("/{cli_id}/assignment")
async def patch_launch_assignment(
    profile_id: str,
    cli_id: str,
    body: LaunchAssignRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    try:
        binding = assign_cli(profile_id, cli_id, body.agent_slot)
    except LaunchServiceError as exc:
        raise _launch_http_error(exc) from exc
    return {"binding": binding}


@router.delete("/{cli_id}/assignment")
async def delete_launch_assignment(
    profile_id: str,
    cli_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    try:
        binding = unassign_cli(profile_id, cli_id)
    except LaunchServiceError as exc:
        raise _launch_http_error(exc) from exc
    return {"binding": binding, "removed": binding is not None}


@router.post("/sessions/{session_ref}/send")
async def post_session_send(
    profile_id: str,
    session_ref: str,
    body: LaunchSendRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    try:
        result = send_session_message(
            profile_id,
            session_ref,
            body.message,
            enter=body.enter,
        )
    except LaunchServiceError as exc:
        raise _launch_http_error(exc) from exc
    return result


@router.get("/sessions/{session_ref}/output")
async def get_session_output(
    profile_id: str,
    session_ref: str,
    lines: int = Query(40, ge=1, le=200),
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    try:
        return capture_session_output(profile_id, session_ref, lines=lines)
    except LaunchServiceError as exc:
        raise _launch_http_error(exc) from exc


@router.delete("/sessions/{session_ref}")
async def delete_session(
    profile_id: str,
    session_ref: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _require_profile(profile_id)
    try:
        return kill_launch_session(profile_id, session_ref)
    except LaunchServiceError as exc:
        raise _launch_http_error(exc) from exc