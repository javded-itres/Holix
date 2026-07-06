"""FastAPI routes for Holix Studio (files API + WebSocket)."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from starlette.requests import Request

from integrations.desktop.security import studio_token_valid
from integrations.desktop.session import StudioSession
from integrations.desktop.workspace_files import (
    WorkspacePathError,
    create_directory,
    delete_path,
    list_tree,
    move_path,
    read_file,
    resolve_studio_workspace_root,
    stat_file,
    upload_file,
    write_file,
)

logger = logging.getLogger(__name__)

STUDIO_PREFIX = "/studio"


class WriteFileBody(BaseModel):
    path: str = Field(..., min_length=1)
    content: str = ""
    create_only: bool = False


class MkdirBody(BaseModel):
    path: str = Field(..., min_length=1)


class DeletePathBody(BaseModel):
    path: str = Field(..., min_length=1)


class MovePathBody(BaseModel):
    source: str = Field(..., min_length=1)
    destination: str = ""
    into: bool = False


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
    serve_cwd: Path | str | None = None,
) -> APIRouter:
    router = APIRouter(prefix=STUDIO_PREFIX)
    studio_session = session or StudioSession(profile)
    studio_workspace_root = resolve_studio_workspace_root(profile, serve_cwd=serve_cwd)
    require_auth = _auth_dependency(auth_token)

    @router.get("/api/health")
    async def studio_health() -> dict[str, str]:
        return {
            "status": "ok",
            "profile": profile,
            "workspace_root": str(studio_workspace_root),
        }

    @router.get("/api/files/tree", dependencies=[Depends(require_auth)])
    async def files_tree(
        root: str = Query("workspace"),
        depth: int = Query(4, ge=1, le=8),
    ) -> dict[str, Any]:
        try:
            return list_tree(
                profile,
                depth=depth,
                root=root,
                workspace_root=studio_workspace_root,
            )
        except WorkspacePathError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.get("/api/files/read", dependencies=[Depends(require_auth)])
    async def files_read(path: str = Query(..., min_length=1)) -> dict[str, Any]:
        try:
            return read_file(profile, path, workspace_root=studio_workspace_root)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except (WorkspacePathError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.get("/api/files/stat", dependencies=[Depends(require_auth)])
    async def files_stat(path: str = Query(..., min_length=1)) -> dict[str, Any]:
        try:
            return stat_file(profile, path, workspace_root=studio_workspace_root)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except WorkspacePathError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.post("/api/files/write", dependencies=[Depends(require_auth)])
    async def files_write(body: WriteFileBody) -> dict[str, Any]:
        try:
            return write_file(
                profile,
                body.path,
                body.content,
                create_only=body.create_only,
                workspace_root=studio_workspace_root,
            )
        except FileExistsError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except (WorkspacePathError, IsADirectoryError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.post("/api/files/mkdir", dependencies=[Depends(require_auth)])
    async def files_mkdir(body: MkdirBody) -> dict[str, Any]:
        try:
            return create_directory(profile, body.path, workspace_root=studio_workspace_root)
        except FileExistsError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except WorkspacePathError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.post("/api/files/delete", dependencies=[Depends(require_auth)])
    async def files_delete(body: DeletePathBody) -> dict[str, Any]:
        try:
            return delete_path(profile, body.path, workspace_root=studio_workspace_root)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except WorkspacePathError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.post("/api/files/move", dependencies=[Depends(require_auth)])
    async def files_move(body: MovePathBody) -> dict[str, Any]:
        try:
            return move_path(
                profile,
                body.source,
                body.destination,
                into=body.into,
                workspace_root=studio_workspace_root,
            )
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except FileExistsError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except NotADirectoryError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except (WorkspacePathError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.post("/api/files/upload", dependencies=[Depends(require_auth)])
    async def files_upload(
        file: UploadFile = File(...),
        directory: str = Form(""),
    ) -> dict[str, Any]:
        try:
            data = await file.read()
            name = file.filename or "upload.bin"
            # Strip any path components browsers may include (e.g. C:\fakepath\file.txt)
            name = Path(name).name
            return upload_file(
                profile,
                directory,
                name,
                data,
                workspace_root=studio_workspace_root,
            )
        except FileExistsError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except (WorkspacePathError, IsADirectoryError, ValueError) as e:
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
                "workspace_root": str(studio_workspace_root),
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
                asyncio.create_task(
                    studio_session.handle_client_message(message),
                    name="studio-ws-message",
                )
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(websocket)
            if not clients:
                studio_session.set_broadcast(_noop_broadcast)

    @router.get("", include_in_schema=False)
    async def studio_index_no_slash(request: Request) -> RedirectResponse:
        """Redirect /studio → /studio/ preserving query string (token)."""
        q = request.url.query
        target = f"{STUDIO_PREFIX}/" + (f"?{q}" if q else "")
        return RedirectResponse(url=target, status_code=307)

    @router.get("/", dependencies=[Depends(require_auth)])
    async def studio_index(request: Request) -> HTMLResponse:
        index = _static_dir() / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=503, detail="Studio static UI not installed")
        html = index.read_text(encoding="utf-8")
        token = request.query_params.get("token") or ""
        if token:
            inject = f'<script>window.HOLIX_STUDIO_TOKEN={json.dumps(token)};</script>'
            html = html.replace("</head>", f"  {inject}\n</head>", 1)
        return HTMLResponse(html)

    @router.get("/assets/{asset_path:path}")
    async def studio_assets(asset_path: str) -> FileResponse:
        base = (_static_dir() / "assets").resolve()
        target = (base / asset_path).resolve()
        if base not in target.parents and target != base:
            raise HTTPException(status_code=404)
        if not target.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(target)

    router.studio_session = studio_session  # type: ignore[attr-defined]
    router.studio_workspace_root = studio_workspace_root  # type: ignore[attr-defined]
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