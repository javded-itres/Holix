"""Hermes-compatible /v1 endpoints (models, capabilities, responses, runs, toolsets)."""

from __future__ import annotations

import asyncio
import json
import time
import uuid

from core.gateway.runs_store import RunStatus
from core.security.permissions import PermissionChecker
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from api import state
from api.deps import (
    RequestContext,
    get_registry,
    resolve_profile_name,
    verify_api_key,
)
from api.schemas.hermes import (
    CapabilitiesResponse,
    ResponsesCreateRequest,
    RunApprovalRequest,
    RunsCreateRequest,
)
from api.services.content_parts import (
    UnsupportedContentTypeError,
    enrich_with_vision_descriptions,
    parse_responses_input,
)

router = APIRouter(prefix="/v1", tags=["hermes"])


def _resolve_ctx(
    key_info: dict,
    model: str | None,
    x_helix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
    x_helix_session_id: str | None = Header(None),
    x_hermes_session_id: str | None = Header(None),
    x_helix_session_key: str | None = Header(None),
    x_hermes_session_key: str | None = Header(None),
) -> RequestContext:
    from api.deps import _header_alias, _validate_session_key

    host = state.host_profile or "default"
    profile = resolve_profile_name(
        header_profile=_header_alias(x_helix_profile, x_hermes_profile),
        model=model,
        host_profile=host,
    )
    session_id = _header_alias(x_helix_session_id, x_hermes_session_id) or "default"
    session_key = _validate_session_key(
        _header_alias(x_helix_session_key, x_hermes_session_key)
    )
    return RequestContext(
        profile=profile,
        conversation_id=session_id,
        session_key=session_key,
        api_key_info=key_info,
    )


@router.get("/models")
async def list_models(
    key_info: dict = Depends(verify_api_key),
    registry=Depends(get_registry),
):
    from cli.core import ProfileManager

    profiles = ProfileManager().list_profiles() or [state.host_profile]
    data = []
    for name in profiles:
        data.append({
            "id": name,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "helix",
        })
    if not data:
        data.append({
            "id": state.host_profile,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "helix",
        })
    return {"object": "list", "data": data}


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities(key_info: dict = Depends(verify_api_key)):
    model_name = state.host_profile or "helix"
    return CapabilitiesResponse(
        model=model_name,
        features={
            "chat_completions": True,
            "responses_api": True,
            "run_submission": True,
            "run_status": True,
            "run_events_sse": True,
            "run_stop": True,
            "run_approval": True,
            "session_list": True,
            "session_chat": True,
            "session_chat_stream": True,
            "jobs_crud": True,
            "jobs_hermes_schema": True,
            "multi_profile": True,
            "multimodal_input": True,
            "session_source_filter": True,
            "hermes_sse_events": True,
        },
        endpoints={
            "chat_completions": "/v1/chat/completions",
            "responses": "/v1/responses",
            "runs": "/v1/runs",
            "models": "/v1/models",
            "skills": "/v1/skills",
            "toolsets": "/v1/toolsets",
            "jobs": "/api/jobs",
            "sessions": "/api/sessions",
            "helix_profiles": "/api/helix/profiles",
        },
    )


@router.get("/toolsets")
async def list_toolsets(
    key_info: dict = Depends(verify_api_key),
    registry=Depends(get_registry),
    x_helix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    ctx = _resolve_ctx(key_info, None, x_helix_profile, x_hermes_profile, None, None, None, None)
    agent = await registry.get_agent(ctx.profile)
    tools = agent.get_tools()
    return [
        {
            "name": "core",
            "label": "Core tools",
            "description": "Helix built-in tools for profile",
            "enabled": True,
            "configured": True,
            "tools": tools,
        }
    ]


@router.get("/skills")
async def list_skills_hermes(
    key_info: dict = Depends(verify_api_key),
    registry=Depends(get_registry),
    x_helix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    ctx = _resolve_ctx(key_info, None, x_helix_profile, x_hermes_profile, None, None, None, None)
    agent = await registry.get_agent(ctx.profile)
    raw = agent.get_skills()
    items = []
    for name, meta in raw.items():
        if isinstance(meta, dict):
            items.append({
                "name": name,
                "description": meta.get("description", ""),
                "category": meta.get("category", meta.get("tags", ["general"])[0] if meta.get("tags") else "general"),
            })
        else:
            items.append({"name": name, "description": "", "category": "general"})
    return items


@router.post("/responses")
async def create_response(
    body: ResponsesCreateRequest,
    key_info: dict = Depends(verify_api_key),
    registry=Depends(get_registry),
    x_helix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
    x_helix_session_id: str | None = Header(None),
    x_hermes_session_id: str | None = Header(None),
    x_helix_session_key: str | None = Header(None),
    x_hermes_session_key: str | None = Header(None),
):
    ctx = _resolve_ctx(
        key_info,
        body.model,
        x_helix_profile,
        x_hermes_profile,
        x_helix_session_id,
        x_hermes_session_id,
        x_helix_session_key,
        x_hermes_session_key,
    )
    checker = PermissionChecker(key_info["permissions"])
    if not checker.can_read():
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    store = state.responses_store
    if body.previous_response_id and store is not None:
        prev = store.get(body.previous_response_id)
        if prev is None:
            raise HTTPException(status_code=404, detail="previous_response_id not found")

    try:
        parsed = parse_responses_input(body.input)
    except UnsupportedContentTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user_input = await enrich_with_vision_descriptions(parsed, profile=ctx.profile)
    if not user_input:
        raise HTTPException(status_code=400, detail="input is required")

    conversation = body.conversation or ctx.conversation_id
    agent = await registry.get_agent(ctx.profile)
    async with state._agent_request_lock:  # type: ignore[attr-defined]
        output = await agent.run(
            user_input=user_input,
            conversation_id=conversation,
        )

    response_payload = {
        "id": f"resp_{uuid.uuid4().hex[:24]}",
        "object": "response",
        "status": "completed",
        "model": ctx.profile,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": output}],
            }
        ],
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }
    if body.store and store is not None:
        stored = store.save(
            profile=ctx.profile,
            payload=response_payload,
            conversation=body.conversation,
        )
        response_payload["id"] = stored.id
    return response_payload


@router.get("/responses/{response_id}")
async def get_response(
    response_id: str,
    key_info: dict = Depends(verify_api_key),
):
    store = state.responses_store
    if store is None:
        raise HTTPException(status_code=503, detail="Responses store unavailable")
    item = store.get(response_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Response not found")
    return item.to_api_dict()


@router.delete("/responses/{response_id}")
async def delete_response(
    response_id: str,
    key_info: dict = Depends(verify_api_key),
):
    store = state.responses_store
    if store is None:
        raise HTTPException(status_code=503, detail="Responses store unavailable")
    if not store.delete(response_id):
        raise HTTPException(status_code=404, detail="Response not found")
    return {"deleted": True, "id": response_id}


async def _execute_run(record, registry) -> None:
    runs = state.runs_store
    if runs is None:
        return
    try:
        runs.update(record.run_id, status=RunStatus.RUNNING)
        agent = await registry.get_agent(record.profile)
        async with state._agent_request_lock:  # type: ignore[attr-defined]
            if record._cancel.is_set():
                runs.update(record.run_id, status=RunStatus.CANCELLED)
                return
            output = await agent.run(
                user_input=record.input_text,
                conversation_id=record.session_id or "default",
            )
        runs.update(
            record.run_id,
            status=RunStatus.COMPLETED,
            output=output,
            usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        )
        runs.append_event(record.run_id, {"type": "run.completed", "output": output})
    except Exception as exc:
        runs.update(record.run_id, status=RunStatus.FAILED, error=str(exc))
        runs.append_event(record.run_id, {"type": "run.failed", "error": str(exc)})


@router.post("/runs")
async def create_run(
    body: RunsCreateRequest,
    key_info: dict = Depends(verify_api_key),
    registry=Depends(get_registry),
):
    ctx = _resolve_ctx(key_info, body.model, None, None, None, None, None, None)
    checker = PermissionChecker(key_info["permissions"])
    if not checker.can_execute() and not checker.can_read():
        raise HTTPException(status_code=403, detail="Execute permission required")

    runs = state.runs_store
    if runs is None:
        raise HTTPException(status_code=503, detail="Runs store unavailable")

    record = runs.create(
        profile=ctx.profile,
        model=body.model,
        input_text=body.input,
        session_id=body.session_id or ctx.conversation_id,
        instructions=body.instructions,
    )
    asyncio.create_task(_execute_run(record, registry))
    return {"run_id": record.run_id, "status": record.status.value}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, key_info: dict = Depends(verify_api_key)):
    runs = state.runs_store
    if runs is None:
        raise HTTPException(status_code=503, detail="Runs store unavailable")
    record = runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return record.to_dict()


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, key_info: dict = Depends(verify_api_key)):
    runs = state.runs_store
    if runs is None:
        raise HTTPException(status_code=503, detail="Runs store unavailable")
    record = runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")

    async def generate():
        sent = 0
        while sent < 120:
            record = runs.get(run_id)
            if record is None:
                break
            while sent < len(record.events):
                payload = record.events[sent]
                sent += 1
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            if record.status in {
                RunStatus.COMPLETED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
            }:
                yield f"data: {json.dumps({'type': 'run.terminal', 'status': record.status.value})}\n\n"
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: str, key_info: dict = Depends(verify_api_key)):
    runs = state.runs_store
    if runs is None:
        raise HTTPException(status_code=503, detail="Runs store unavailable")
    if not runs.request_cancel(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return {"status": "stopping", "run_id": run_id}


@router.post("/runs/{run_id}/approval")
async def approve_run(
    run_id: str,
    body: RunApprovalRequest,
    key_info: dict = Depends(verify_api_key),
):
    runs = state.runs_store
    if runs is None:
        raise HTTPException(status_code=503, detail="Runs store unavailable")
    if not runs.resolve_approval(run_id, body.model_dump()):
        raise HTTPException(status_code=404, detail="Run not found")
    return {"status": "recorded", "run_id": run_id, "decision": body.decision}