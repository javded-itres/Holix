"""FastAPI routes for Holix Studio (files API + WebSocket)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from starlette.requests import Request

from integrations.desktop.security import studio_token_valid
from integrations.desktop.session import StudioSession
from integrations.desktop.workspace_files import (
    WorkspacePathError,
    list_tree,
    read_file,
    stat_file,
)

logger = logging.getLogger(__name__)

STUDIO_PREFIX = "/studio"


def _static_dir() -> Path:
    return Path(__file__).resolve().parent / "static"


def _auth_dependency(expected_token: str | None):
    async def _require_studio_auth(request: Request) -> None:
        if not expected_token:
            return
        q = request.query_params.get("token")
        if studio_token_valid(request.headers.get("Authorization"), q, expected_token):
            return
        raise HTTPException(status_code=401, detail="Missing or invalid Studio token")

    return _require_studio_auth


def create_studio_router(
    *,
    profile: str,
    auth_token: str | None = None,
    session: StudioSession | None = None,
) -> APIRouter:
    router = APIRouter(prefix=STUDIO_PREFIX)
    studio_session = session or StudioSession(profile)
    require_auth = _auth_dependency(auth_token)

    @router.get("/api/health")
    async def studio_health() -> dict[str, str]:
        return {"status": "ok", "profile": profile}

    @router.get("/api/files/tree", dependencies=[Depends(require_auth)])
    async def files_tree(
        root: str = Query("workspace"),
        depth: int = Query(4, ge=1, le=8),
    ) -> dict[str, Any]:
        try:
            return list_tree(profile, depth=depth, root=root)
        except WorkspacePathError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.get("/api/files/read", dependencies=[Depends(require_auth)])
    async def files_read(path: str = Query(..., min_length=1)) -> dict[str, Any]:
        try:
            return read_file(profile, path)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except (WorkspacePathError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.get("/api/files/stat", dependencies=[Depends(require_auth)])
    async def files_stat(path: str = Query(..., min_length=1)) -> dict[str, Any]:
        try:
            return stat_file(profile, path)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except WorkspacePathError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.websocket("/ws")
    async def studio_ws(websocket: WebSocket) -> None:
        if auth_token:
            q = websocket.query_params.get("token")
            if not studio_token_valid(
                websocket.headers.get("Authorization"),
                q,
                auth_token,
            ):
                await websocket.close(code=4401, reason="Unauthorized")
                return
        await websocket.accept()
        clients: set[WebSocket] = {websocket}

        async def broadcast(payload: dict[str, Any]) -> None:
            dead: list[WebSocket] = []
            data = json.dumps(payload, default=str)
            for client in clients:
                try:
                    await client.send_text(data)
                except Exception:
                    dead.append(client)
            for client in dead:
                clients.discard(client)

        studio_session.set_broadcast(broadcast)
        await websocket.send_json(
            {
                "type": "connected",
                "profile": profile,
                "conversation_id": studio_session.conversation_id,
            }
        )
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                    continue
                if not isinstance(message, dict):
                    continue
                await studio_session.handle_client_message(message)
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(websocket)
            if not clients:
                studio_session.set_broadcast(_noop_broadcast)

    @router.get("/", dependencies=[Depends(require_auth)])
    async def studio_index() -> FileResponse:
        index = _static_dir() / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=503, detail="Studio static UI not installed")
        return FileResponse(index)

    @router.get("/assets/{asset_path:path}", dependencies=[Depends(require_auth)])
    async def studio_assets(asset_path: str) -> FileResponse:
        base = _static_dir().resolve()
        target = (base / asset_path).resolve()
        if base not in target.parents and target != base:
            raise HTTPException(status_code=404)
        if not target.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(target)

    router.studio_session = studio_session  # type: ignore[attr-defined]
    return router


async def _noop_broadcast(_payload: dict[str, Any]) -> None:
    return None


def mount_studio_on_gateway(app: Any, *, profile: str | None = None) -> None:
    """Attach Studio routes to an existing FastAPI gateway app."""
    import os

    if os.getenv("HOLIX_STUDIO_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return
    host_profile = profile or (os.getenv("HOLIX_PROFILE") or "default").strip() or "default"
    token = os.getenv("HOLIX_STUDIO_TOKEN", "").strip() or None
    router = create_studio_router(profile=host_profile, auth_token=token)
    app.include_router(router)