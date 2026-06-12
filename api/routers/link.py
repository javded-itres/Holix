"""Holix Link — pairing REST API and WebSocket relay."""

from __future__ import annotations

import hashlib
import time

from cli.core import ProfileManager
from core.gateway.link_relay import LinkRelay
from core.gateway.links_store import LinksStore, link_connected_iso, pair_code_expires_iso
from fastapi import APIRouter, Depends, Header, HTTPException, WebSocket, WebSocketDisconnect
from integrations.link.protocol import (
    AuthMessage,
    AuthOkMessage,
    ErrorMessage,
    LinkStatusResponse,
    PairCreateRequest,
    PairCreateResponse,
    PairExchangeRequest,
    PairExchangeResponse,
    WsMessageType,
)
from integrations.link.settings import load_link_profile_settings
from starlette.requests import Request as StarletteRequest

from api import state
from api.deps import verify_api_key
from api.services.holix_deps import profile_access

router = APIRouter(prefix="/v1/link", tags=["holix-link"])


def _links_store() -> LinksStore:
    if state.links_store is None:
        state.links_store = LinksStore()
    return state.links_store


def _link_relay() -> LinkRelay:
    if state.link_relay is None:
        state.link_relay = LinkRelay()
    return state.link_relay


def server_fingerprint() -> str:
    from core.platform_compat import resolve_holix_home

    digest = hashlib.sha256(str(resolve_holix_home()).encode()).hexdigest()
    return digest[:16]


def _ws_url(request: StarletteRequest) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host") or f"{request.url.hostname}:{request.url.port}"
    scheme = "wss" if forwarded_proto == "https" else "ws"
    return f"{scheme}://{host}/v1/link/ws"


def _check_public_rate_limit(request: StarletteRequest) -> None:
    limiter = state.rate_limiter
    if limiter is None:
        return
    client_host = request.client.host if request.client else "unknown"
    from config import settings

    if not limiter.check_rate_limit(f"link-pair:{client_host}", settings.public_rate_limit_rpm):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")


def _require_profile_exists(profile: str) -> None:
    manager = ProfileManager()
    if not manager.profile_exists(profile):
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")


def _authorize_link_profile(
    profile: str,
    key_info: dict,
    x_holix_profile: str | None,
    x_holix_profile_key: str | None,
) -> None:
    _require_profile_exists(profile)
    profile_access(profile, key_info, x_holix_profile, x_holix_profile_key)


def _authorize_link_record(
    link_id: str,
    key_info: dict,
    x_holix_profile: str | None,
    x_holix_profile_key: str | None,
):
    store = _links_store()
    record = store.get_link(link_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Link not found")
    _authorize_link_profile(record.profile, key_info, x_holix_profile, x_holix_profile_key)
    return record


@router.post("/create", response_model=PairCreateResponse)
async def create_pair_code(
    body: PairCreateRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    """Create a one-time pairing code for a server profile (admin or profile owner)."""
    profile = body.profile.strip()
    if not profile:
        raise HTTPException(status_code=400, detail="Profile is required")

    _authorize_link_profile(profile, key_info, x_holix_profile, x_holix_profile_key)

    store = _links_store()
    store.purge_expired_pair_codes()
    record = store.create_pair_code(
        profile=profile,
        ttl_seconds=body.ttl_seconds,
        created_by=key_info.get("name") or key_info.get("id"),
    )
    return PairCreateResponse(
        code=record.code,
        expires_at=pair_code_expires_iso(record),
        profile=record.profile,
    )


@router.post("/pair", response_model=PairExchangeResponse)
async def exchange_pair_code(body: PairExchangeRequest, request: StarletteRequest):
    """Exchange pairing code for link credentials (client, no API key)."""
    _check_public_rate_limit(request)

    code = body.code.strip().upper()
    folder = body.folder.strip()
    device_key = body.device_public_key_b64.strip()
    if not code or not folder or not device_key:
        raise HTTPException(status_code=400, detail="code, folder, and device_public_key_b64 are required")

    store = _links_store()
    store.purge_expired_pair_codes()
    pair = store.get_pair_code(code)
    if pair is None:
        raise HTTPException(status_code=404, detail="Invalid pairing code")
    if pair.used:
        raise HTTPException(status_code=410, detail="Pairing code already used")
    if pair.expires_at < time.time():
        raise HTTPException(status_code=410, detail="Pairing code expired")

    settings = load_link_profile_settings(pair.profile)
    active_count = store.count_active_links(pair.profile)
    if active_count >= settings.max_connections:
        raise HTTPException(
            status_code=409,
            detail=f"Profile '{pair.profile}' reached link limit ({settings.max_connections})",
        )

    link = store.create_link(
        profile=pair.profile,
        folder_portable=folder,
        device_public_key_b64=device_key,
        permissions=settings.permissions,
    )
    store.mark_pair_code_used(code)

    return PairExchangeResponse(
        link_id=link.link_id,
        gateway_ws_url=_ws_url(request),
        server_fingerprint=server_fingerprint(),
        permissions=link.permissions,
    )


@router.get("/list")
async def list_links(
    profile: str | None = None,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    """List active links (optionally filtered by profile)."""
    store = _links_store()
    relay = _link_relay()

    target = (profile or "").strip() or None
    if target:
        _authorize_link_profile(target, key_info, x_holix_profile, x_holix_profile_key)
        records = store.list_links(profile=target)
    else:
        from api.services.profile_access import require_admin_access

        ctx = profile_access(state.host_profile, key_info, x_holix_profile, x_holix_profile_key)
        require_admin_access(ctx)
        records = store.list_links()

    links = [
        LinkStatusResponse(
            link_id=rec.link_id,
            profile=rec.profile,
            folder_portable=rec.folder_portable,
            online=relay.is_online(rec.link_id),
            connected_at=link_connected_iso(rec),
            status=rec.status,
        ).model_dump()
        for rec in records
    ]
    return {"links": links, "count": len(links)}


@router.get("/{link_id}", response_model=LinkStatusResponse)
async def get_link_status(
    link_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    record = _authorize_link_record(link_id, key_info, x_holix_profile, x_holix_profile_key)
    relay = _link_relay()
    return LinkStatusResponse(
        link_id=record.link_id,
        profile=record.profile,
        folder_portable=record.folder_portable,
        online=relay.is_online(record.link_id),
        connected_at=link_connected_iso(record),
        status=record.status,
    )


@router.post("/revoke/{link_id}")
async def revoke_link(
    link_id: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    record = _authorize_link_record(link_id, key_info, x_holix_profile, x_holix_profile_key)
    store = _links_store()
    relay = _link_relay()

    if record.status != "active":
        raise HTTPException(status_code=409, detail="Link is not active")

    revoked = store.revoke_link(link_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Link not found")

    websocket = relay._connections.get(link_id)  # noqa: SLF001
    if websocket is not None:
        try:
            await websocket.close(code=1008, reason="revoked")
        except Exception:
            pass
        await relay.unregister(link_id, websocket)

    return {"status": "revoked", "link_id": link_id}


@router.websocket("/ws")
async def link_websocket(websocket: WebSocket):
    """Persistent outbound WebSocket for Holix Link clients."""
    await websocket.accept()
    store = _links_store()
    relay = _link_relay()
    link_id: str | None = None

    try:
        raw = await websocket.receive_json()
        if raw.get("type") != WsMessageType.AUTH:
            err = ErrorMessage(code="auth_required", message="First message must be type=auth")
            await websocket.send_json(err.model_dump())
            await websocket.close(code=1008)
            return

        auth = AuthMessage.model_validate(raw)
        record = store.get_link(auth.link_id)
        if record is None or record.status != "active":
            err = ErrorMessage(code="invalid_link", message="Unknown or inactive link")
            await websocket.send_json(err.model_dump())
            await websocket.close(code=1008)
            return

        if record.device_public_key_b64 != auth.device_public_key_b64.strip():
            err = ErrorMessage(code="invalid_key", message="Device public key mismatch")
            await websocket.send_json(err.model_dump())
            await websocket.close(code=1008)
            return

        link_id = record.link_id
        await relay.register(link_id, websocket)
        store.set_connected(link_id, connected=True)

        ok = AuthOkMessage(
            link_id=link_id,
            permissions=record.permissions,
        )
        await websocket.send_json(ok.model_dump())

        while True:
            incoming = await websocket.receive_json()
            outbound = await relay.handle_client_message(link_id, incoming)
            if outbound is not None:
                await websocket.send_json(outbound)

    except WebSocketDisconnect:
        pass
    except Exception:
        err = ErrorMessage(code="relay_error", message="Link relay error")
        try:
            await websocket.send_json(err.model_dump())
        except Exception:
            pass
    finally:
        if link_id is not None:
            await relay.unregister(link_id, websocket)
            store.set_connected(link_id, connected=False)