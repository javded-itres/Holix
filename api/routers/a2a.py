"""A2A (Agent2Agent) protocol endpoints for Holix gateway."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from api.deps import ensure_key_profile_allowed, resolve_profile_name, verify_api_key
from api.di import GatewayLocks, HostProfileName, ProfileAgentRegistry
from api.errors import sse_streaming_response
from api.services.path_visibility import gateway_agent_path_visibility
from core.a2a.card import build_agent_card
from core.a2a.config import load_a2a_config
from core.a2a.server import (
    cancel_task,
    get_task_public,
    handle_message_send,
    handle_message_stream,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["a2a"], route_class=DishkaRoute)

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _profile_from_headers(
    key_info: dict,
    host_profile: str,
    x_holix_profile: str | None,
    x_hermes_profile: str | None,
) -> str:
    from api.deps import _header_alias

    profile = resolve_profile_name(
        header_profile=_header_alias(x_holix_profile, x_hermes_profile),
        model=None,
        host_profile=host_profile or "default",
    )
    ensure_key_profile_allowed(key_info, profile)
    return profile


def _public_base(request: Request, cfg_url: str | None) -> str:
    if cfg_url:
        return cfg_url.rstrip("/")
    # Reconstruct from request
    root = str(request.base_url).rstrip("/")
    return f"{root}/a2a"


def _require_a2a(profile: str) -> None:
    cfg = load_a2a_config(profile)
    if not cfg.server_enabled:
        raise HTTPException(
            status_code=404,
            detail="A2A is disabled for this profile (a2a.enabled / HOLIX_A2A_ENABLED)",
        )


@router.get("/.well-known/agent.json")
@router.get("/.well-known/agent-card.json")
async def well_known_agent_card(
    request: Request,
    host_profile: FromDishka[HostProfileName],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    """Public Agent Card discovery (authenticated with gateway API key)."""
    profile = _profile_from_headers(
        key_info, str(host_profile), x_holix_profile, x_hermes_profile
    )
    _require_a2a(profile)
    cfg = load_a2a_config(profile)
    public = _public_base(request, cfg.public_url)
    return build_agent_card(profile, public_url=public, config=cfg)


@router.get("/a2a/.well-known/agent.json")
@router.get("/a2a/agent-card")
async def a2a_agent_card(
    request: Request,
    host_profile: FromDishka[HostProfileName],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    profile = _profile_from_headers(
        key_info, str(host_profile), x_holix_profile, x_hermes_profile
    )
    _require_a2a(profile)
    cfg = load_a2a_config(profile)
    public = _public_base(request, cfg.public_url)
    return build_agent_card(profile, public_url=public, config=cfg)


def _jsonrpc_error(
    req_id: Any, code: int, message: str, *, http_status: int = 200
) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        },
    )


def _sse_data(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


async def _jsonrpc_stream(
    *,
    req_id: Any,
    agent: Any,
    message: Any,
    profile: str,
    configuration: dict[str, Any] | None,
    key_info: dict,
    locks: Any,
) -> AsyncIterator[str]:
    """SSE stream of JSON-RPC responses (one result object per event)."""
    try:
        async with locks.agent_request:
            with gateway_agent_path_visibility(agent, key_info):
                async for item in handle_message_stream(
                    agent=agent,
                    message=message,
                    profile=profile,
                    configuration=configuration,
                ):
                    yield _sse_data(
                        {"jsonrpc": "2.0", "id": req_id, "result": item}
                    )
    except ValueError as exc:
        yield _sse_data(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": str(exc)},
            }
        )
    except Exception as exc:
        logger.exception("A2A message/stream failed")
        yield _sse_data(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(exc)},
            }
        )


async def _rest_stream(
    *,
    agent: Any,
    message: Any,
    profile: str,
    configuration: dict[str, Any] | None,
    key_info: dict,
    locks: Any,
) -> AsyncIterator[str]:
    """SSE stream of bare StreamResponse objects (REST binding)."""
    try:
        async with locks.agent_request:
            with gateway_agent_path_visibility(agent, key_info):
                async for item in handle_message_stream(
                    agent=agent,
                    message=message,
                    profile=profile,
                    configuration=configuration,
                ):
                    yield _sse_data(item)
    except ValueError as exc:
        yield _sse_data({"error": {"code": "invalid_params", "message": str(exc)}})
    except Exception as exc:
        logger.exception("A2A REST stream failed")
        yield _sse_data({"error": {"code": "internal", "message": str(exc)}})


@router.post("/a2a")
@router.post("/a2a/")
async def a2a_jsonrpc(
    request: Request,
    locks: FromDishka[GatewayLocks],
    registry: FromDishka[ProfileAgentRegistry],
    host_profile: FromDishka[HostProfileName],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    """JSON-RPC 2.0: message/send, message/stream (SSE), tasks/*, agent card."""
    profile = _profile_from_headers(
        key_info, str(host_profile), x_holix_profile, x_hermes_profile
    )
    _require_a2a(profile)

    try:
        body = await request.json()
    except Exception:
        return _jsonrpc_error(None, -32700, "Parse error")

    if not isinstance(body, dict):
        return _jsonrpc_error(None, -32600, "Invalid Request")

    req_id = body.get("id")
    method = str(body.get("method") or "").strip()
    params = body.get("params") if isinstance(body.get("params"), dict) else {}

    if method in {"agent/getAuthenticatedExtendedCard", "agent/card", "get_agent_card"}:
        cfg = load_a2a_config(profile)
        public = _public_base(request, cfg.public_url)
        card = build_agent_card(profile, public_url=public, config=cfg)
        return {"jsonrpc": "2.0", "id": req_id, "result": card}

    if method in {
        "message/stream",
        "message/sendStreamingMessage",
        "message/sendSubscribe",
        "send_streaming_message",
    }:
        message = params.get("message")
        if not message:
            return _jsonrpc_error(req_id, -32602, "params.message is required")
        configuration = params.get("configuration")
        agent = await registry.get_agent(profile)
        return sse_streaming_response(
            _jsonrpc_stream(
                req_id=req_id,
                agent=agent,
                message=message,
                profile=profile,
                configuration=configuration
                if isinstance(configuration, dict)
                else None,
                key_info=key_info,
                locks=locks,
            )
        )

    if method in {"message/send", "message/sendMessage", "send_message"}:
        message = params.get("message")
        if not message:
            return _jsonrpc_error(req_id, -32602, "params.message is required")
        configuration = params.get("configuration")
        agent = await registry.get_agent(profile)
        # Optional: stream if client asks via Accept
        accept = (request.headers.get("accept") or "").lower()
        if "text/event-stream" in accept:
            return sse_streaming_response(
                _jsonrpc_stream(
                    req_id=req_id,
                    agent=agent,
                    message=message,
                    profile=profile,
                    configuration=configuration
                    if isinstance(configuration, dict)
                    else None,
                    key_info=key_info,
                    locks=locks,
                )
            )
        try:
            async with locks.agent_request:
                with gateway_agent_path_visibility(agent, key_info):
                    result = await handle_message_send(
                        agent=agent,
                        message=message,
                        profile=profile,
                        configuration=configuration
                        if isinstance(configuration, dict)
                        else None,
                    )
        except ValueError as exc:
            return _jsonrpc_error(req_id, -32602, str(exc))
        except Exception as exc:
            logger.exception("A2A message/send failed")
            return _jsonrpc_error(req_id, -32000, str(exc))
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    if method in {"tasks/get", "tasks/getTask", "get_task"}:
        task_id = str(params.get("id") or params.get("taskId") or "").strip()
        if not task_id:
            return _jsonrpc_error(req_id, -32602, "params.id is required")
        hist = params.get("historyLength")
        try:
            hist_n = int(hist) if hist is not None else None
        except (TypeError, ValueError):
            hist_n = None
        task = get_task_public(task_id, history_length=hist_n, profile=profile)
        if task is None:
            return _jsonrpc_error(req_id, -32001, "Task not found")
        return {"jsonrpc": "2.0", "id": req_id, "result": task}

    if method in {"tasks/cancel", "tasks/cancelTask", "cancel_task"}:
        task_id = str(params.get("id") or params.get("taskId") or "").strip()
        if not task_id:
            return _jsonrpc_error(req_id, -32602, "params.id is required")
        task = cancel_task(task_id, profile=profile)
        if task is None:
            return _jsonrpc_error(req_id, -32001, "Task not found")
        return {"jsonrpc": "2.0", "id": req_id, "result": task}

    if method in {"tasks/list", "list_tasks"}:
        from core.a2a.store import get_a2a_task_store

        context_id = params.get("contextId") or params.get("context_id")
        limit = params.get("pageSize") or params.get("limit") or 50
        try:
            limit_n = int(limit)
        except (TypeError, ValueError):
            limit_n = 50
        tasks = get_a2a_task_store().list_tasks(
            profile=profile,
            context_id=str(context_id) if context_id else None,
            limit=limit_n,
        )
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tasks": [t.to_public_dict(history_length=0) for t in tasks],
                "nextPageToken": "",
                "pageSize": limit_n,
                "totalSize": len(tasks),
            },
        }

    return _jsonrpc_error(req_id, -32601, f"Method not found: {method}")


@router.post("/a2a/message:send")
async def a2a_rest_message_send(
    request: Request,
    locks: FromDishka[GatewayLocks],
    registry: FromDishka[ProfileAgentRegistry],
    host_profile: FromDishka[HostProfileName],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    """HTTP+JSON REST-style Send Message (A2A REST binding subset).

    Send ``Accept: text/event-stream`` to receive SSE StreamResponse events
    instead of a single completed Task JSON body.
    """
    profile = _profile_from_headers(
        key_info, str(host_profile), x_holix_profile, x_hermes_profile
    )
    _require_a2a(profile)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be an object")
    message = body.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="message is required")
    agent = await registry.get_agent(profile)
    configuration = (
        body.get("configuration")
        if isinstance(body.get("configuration"), dict)
        else None
    )
    accept = (request.headers.get("accept") or "").lower()
    if "text/event-stream" in accept:
        return sse_streaming_response(
            _rest_stream(
                agent=agent,
                message=message,
                profile=profile,
                configuration=configuration,
                key_info=key_info,
                locks=locks,
            )
        )
    try:
        async with locks.agent_request:
            with gateway_agent_path_visibility(agent, key_info):
                return await handle_message_send(
                    agent=agent,
                    message=message,
                    profile=profile,
                    configuration=configuration,
                )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/a2a/message:stream")
async def a2a_rest_message_stream(
    request: Request,
    locks: FromDishka[GatewayLocks],
    registry: FromDishka[ProfileAgentRegistry],
    host_profile: FromDishka[HostProfileName],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    """REST streaming Send Message — always ``text/event-stream``."""
    profile = _profile_from_headers(
        key_info, str(host_profile), x_holix_profile, x_hermes_profile
    )
    _require_a2a(profile)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    if not isinstance(body, dict) or not body.get("message"):
        raise HTTPException(status_code=400, detail="message is required")
    agent = await registry.get_agent(profile)
    return sse_streaming_response(
        _rest_stream(
            agent=agent,
            message=body["message"],
            profile=profile,
            configuration=body.get("configuration")
            if isinstance(body.get("configuration"), dict)
            else None,
            key_info=key_info,
            locks=locks,
        )
    )


@router.get("/a2a/tasks/{task_id}")
async def a2a_rest_get_task(
    task_id: str,
    host_profile: FromDishka[HostProfileName],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
    historyLength: int | None = None,
):
    profile = _profile_from_headers(
        key_info, str(host_profile), x_holix_profile, x_hermes_profile
    )
    _require_a2a(profile)
    task = get_task_public(task_id, history_length=historyLength, profile=profile)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/a2a/tasks/{task_id}/subscribe")
async def a2a_rest_subscribe_task(
    task_id: str,
    host_profile: FromDishka[HostProfileName],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    """SSE snapshot for an existing task (terminal or current state).

    For in-flight tasks started via blocking send, returns current state then
    closes. Prefer ``message/stream`` for live progress during a new run.
    """
    profile = _profile_from_headers(
        key_info, str(host_profile), x_holix_profile, x_hermes_profile
    )
    _require_a2a(profile)
    task = get_task_public(task_id, profile=profile)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    async def _gen() -> AsyncIterator[str]:
        yield _sse_data({"task": task})
        state = ((task.get("status") or {}).get("state") or "").lower()
        terminal = state in {
            "completed",
            "failed",
            "canceled",
            "cancelled",
            "rejected",
        }
        yield _sse_data(
            {
                "statusUpdate": {
                    "taskId": task.get("id"),
                    "contextId": task.get("contextId"),
                    "status": task.get("status"),
                    "final": terminal,
                }
            }
        )

    return StreamingResponse(
        _gen(), media_type="text/event-stream", headers=_SSE_HEADERS
    )
