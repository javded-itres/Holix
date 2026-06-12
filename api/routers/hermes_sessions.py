"""Hermes-compatible /api/sessions endpoints."""

from __future__ import annotations

import json

from core.security.permissions import PermissionChecker
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from api import state
from api.deps import get_registry, resolve_profile_name, verify_api_key
from api.schemas.hermes import SessionChatRequest, SessionCreateRequest, SessionPatchRequest
from api.services.content_parts import (
    UnsupportedContentTypeError,
    enrich_with_vision_descriptions,
    parse_content_parts,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _sessions_store():
    if state.sessions_store is None:
        raise HTTPException(status_code=503, detail="Sessions store unavailable")
    return state.sessions_store


def _profile(
    x_holix_profile: str | None,
    x_hermes_profile: str | None,
    body_profile: str | None = None,
) -> str:
    from api.deps import _header_alias

    return resolve_profile_name(
        header_profile=_header_alias(x_holix_profile, x_hermes_profile) or body_profile,
        model=None,
        host_profile=state.host_profile or "default",
    )


@router.get("")
async def list_sessions(
    limit: int = 50,
    offset: int = 0,
    source: str = "all",
    include_children: bool = True,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    store = _sessions_store()
    profile = _profile(x_holix_profile, x_hermes_profile)
    sessions = store.list(
        profile=profile,
        limit=limit,
        offset=offset,
        source=source,
        include_children=include_children,
    )
    return {"sessions": [s.to_dict() for s in sessions], "count": len(sessions)}


@router.post("")
async def create_session(
    body: SessionCreateRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    store = _sessions_store()
    profile = _profile(x_holix_profile, x_hermes_profile, body.profile)
    session = store.create(profile=profile, title=body.title, source=body.source or "api")
    return session.to_dict()


@router.get("/{session_id}")
async def get_session(session_id: str, key_info: dict = Depends(verify_api_key)):
    store = _sessions_store()
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_dict()


@router.patch("/{session_id}")
async def patch_session(
    session_id: str,
    body: SessionPatchRequest,
    key_info: dict = Depends(verify_api_key),
):
    store = _sessions_store()
    session = store.update(
        session_id,
        title=body.title,
        end_reason=body.end_reason,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_dict()


@router.delete("/{session_id}")
async def delete_session(session_id: str, key_info: dict = Depends(verify_api_key)):
    store = _sessions_store()
    if not store.delete(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True, "id": session_id}


@router.get("/{session_id}/messages")
async def session_messages(
    session_id: str,
    limit: int = 50,
    key_info: dict = Depends(verify_api_key),
    registry=Depends(get_registry),
):
    store = _sessions_store()
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    agent = await registry.get_agent(session.profile)
    messages = await agent.get_conversation_history(session.conversation_id, limit)
    return {"session_id": session_id, "messages": messages, "count": len(messages)}


@router.post("/{session_id}/fork")
async def fork_session(
    session_id: str,
    body: SessionCreateRequest,
    key_info: dict = Depends(verify_api_key),
):
    store = _sessions_store()
    child = store.fork(session_id, title=body.title)
    if child is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return child.to_dict()


@router.post("/{session_id}/chat")
async def session_chat(
    session_id: str,
    body: SessionChatRequest,
    key_info: dict = Depends(verify_api_key),
    registry=Depends(get_registry),
):
    store = _sessions_store()
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    checker = PermissionChecker(key_info["permissions"])
    if not checker.can_read():
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    try:
        parsed = parse_content_parts(body.input)
    except UnsupportedContentTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user_input = await enrich_with_vision_descriptions(parsed, profile=session.profile)
    if not user_input:
        raise HTTPException(status_code=400, detail="input is required")

    agent = await registry.get_agent(session.profile)
    async with state._agent_request_lock:  # type: ignore[attr-defined]
        output = await agent.run(
            user_input=user_input,
            conversation_id=session.conversation_id,
        )
    store.update(session_id)
    return {
        "session_id": session_id,
        "output": output,
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }


@router.post("/{session_id}/chat/stream")
async def session_chat_stream(
    session_id: str,
    body: SessionChatRequest,
    key_info: dict = Depends(verify_api_key),
    registry=Depends(get_registry),
):
    from core.loop_streaming import StreamingAgentLoop

    store = _sessions_store()
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        parsed = parse_content_parts(body.input)
    except UnsupportedContentTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user_input = await enrich_with_vision_descriptions(parsed, profile=session.profile)
    if not user_input:
        raise HTTPException(status_code=400, detail="input is required")

    agent = await registry.get_agent(session.profile)
    streaming_loop = StreamingAgentLoop(agent)

    async def generate():
        async with state._agent_request_lock:  # type: ignore[attr-defined]
            async for chunk in streaming_loop.run_conversation_stream(
                user_input=user_input,
                conversation_id=session.conversation_id,
            ):
                yield chunk
        yield f"data: {json.dumps({'type': 'run.completed', 'session_id': session_id})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )