"""Existing Holix /v1 agent endpoints (chat, tools, memory, permissions, plans)."""

from __future__ import annotations

import time

from core.loop_streaming import StreamingAgentLoop
from core.security.permissions import PermissionChecker
from fastapi import APIRouter, Depends, Header, HTTPException
from api import state
from api.deps import get_registry, resolve_profile_name, verify_api_key
from api.errors import _SSE_ERROR_CHUNK, sse_streaming_response
from api.models import ChatCompletionRequest, ChatCompletionResponse
from api.services.content_parts import (
    UnsupportedContentTypeError,
    enrich_with_vision_descriptions,
    parse_content_parts,
)
from api.services.path_visibility import gateway_agent_path_visibility

router = APIRouter(prefix="/v1", tags=["agent"])


def _ctx_from_headers(
    key_info: dict,
    model: str | None,
    x_holix_profile: str | None,
    x_hermes_profile: str | None,
    x_holix_session_id: str | None,
    x_hermes_session_id: str | None,
):
    from api.deps import _header_alias

    host = state.host_profile or "default"
    profile = resolve_profile_name(
        header_profile=_header_alias(x_holix_profile, x_hermes_profile),
        model=model,
        host_profile=host,
    )
    session_id = _header_alias(x_holix_session_id, x_hermes_session_id) or "default"
    return profile, session_id, key_info


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest,
    key_info: dict = Depends(verify_api_key),
    registry=Depends(get_registry),
    x_holix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
    x_holix_session_id: str | None = Header(None),
    x_hermes_session_id: str | None = Header(None),
):
    profile, session_id, key_info = _ctx_from_headers(
        key_info,
        request.model,
        x_holix_profile,
        x_hermes_profile,
        x_holix_session_id,
        x_hermes_session_id,
    )
    checker = PermissionChecker(key_info["permissions"])
    if not checker.can_read():
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    agent = await registry.get_agent(profile)
    if not agent._initialized:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    user_messages = [msg for msg in request.messages if msg.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")
    try:
        parsed = parse_content_parts(user_messages[-1].content)
    except UnsupportedContentTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user_input = await enrich_with_vision_descriptions(parsed, profile=profile)
    if not user_input:
        raise HTTPException(status_code=400, detail="No user message found")
    conversation_id = request.conversation_id or session_id

    if request.stream:
        streaming_loop = StreamingAgentLoop(agent)

        async def generate():
            try:
                async with state._agent_request_lock:  # type: ignore[attr-defined]
                    with gateway_agent_path_visibility(agent, key_info):
                        async for chunk in streaming_loop.run_conversation_stream(
                            user_input=user_input,
                            conversation_id=conversation_id,
                        ):
                            yield chunk
            except Exception:
                yield _SSE_ERROR_CHUNK

        return sse_streaming_response(generate())

    try:
        start_time = time.time()
        async with state._agent_request_lock:  # type: ignore[attr-defined]
            with gateway_agent_path_visibility(agent, key_info):
                response = await agent.run(
                    user_input=user_input,
                    conversation_id=conversation_id,
                )
        elapsed_time = time.time() - start_time
        return ChatCompletionResponse(
            id=f"chatcmpl-{int(time.time())}",
            object="chat.completion",
            created=int(time.time()),
            model=profile,
            choices=[{
                "index": 0,
                "message": {"role": "assistant", "content": response},
                "finish_reason": "stop",
            }],
            usage={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "elapsed_seconds": max(0, int(round(elapsed_time))),
            },
        )
    except Exception as e:
        from api.errors import agent_error_to_http

        raise agent_error_to_http(e) from e


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    limit: int = 30,
    key_info: dict = Depends(verify_api_key),
    registry=Depends(get_registry),
    x_holix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    profile, _, _ = _ctx_from_headers(
        key_info, None, x_holix_profile, x_hermes_profile, None, None
    )
    agent = await registry.get_agent(profile)
    history = await agent.get_conversation_history(conversation_id, limit)
    return {"conversation_id": conversation_id, "messages": history, "count": len(history)}


@router.get("/tools")
async def list_tools(
    key_info: dict = Depends(verify_api_key),
    registry=Depends(get_registry),
    x_holix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    profile, _, _ = _ctx_from_headers(
        key_info, None, x_holix_profile, x_hermes_profile, None, None
    )
    agent = await registry.get_agent(profile)
    tools = agent.get_tools()
    return {"tools": tools, "count": len(tools)}


@router.post("/search")
async def search_memory(
    query: str,
    top_k: int = 5,
    key_info: dict = Depends(verify_api_key),
    registry=Depends(get_registry),
    x_holix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    profile, _, _ = _ctx_from_headers(
        key_info, None, x_holix_profile, x_hermes_profile, None, None
    )
    agent = await registry.get_agent(profile)
    results = await agent.search_memory(query, top_k)
    return {"query": query, "results": results, "count": len(results)}


@router.post("/permissions/grant")
async def grant_permission(
    tool_name: str,
    risk_level: str = "high",
    scope: str = "session",
    argument_pattern: str | None = None,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    from core.security.confirmation import PermissionScope, get_permission_manager_for_profile
    from core.security.confirmation import RiskLevel as RL

    checker = PermissionChecker(key_info["permissions"])
    if not checker.can_execute():
        raise HTTPException(status_code=403, detail="Execute permission required")
    profile, _, _ = _ctx_from_headers(
        key_info, None, x_holix_profile, x_hermes_profile, None, None
    )
    permission_manager = get_permission_manager_for_profile(profile)
    try:
        risk_enum = RL(risk_level)
        scope_enum = PermissionScope(scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    permission_manager.grant(tool_name, scope_enum, risk_enum, argument_pattern)
    return {"status": "granted", "tool_name": tool_name, "scope": scope, "risk_level": risk_level}


@router.get("/permissions")
async def list_permissions(
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    from core.security.confirmation import get_permission_manager_for_profile

    profile, _, _ = _ctx_from_headers(
        key_info, None, x_holix_profile, x_hermes_profile, None, None
    )
    return get_permission_manager_for_profile(profile).list_grants()


@router.delete("/permissions/{grant_key}")
async def revoke_permission(
    grant_key: str,
    scope: str = "always",
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    from core.security.confirmation import PermissionScope, get_permission_manager_for_profile
    from core.security.confirmation import RiskLevel as RL

    profile, _, _ = _ctx_from_headers(
        key_info, None, x_holix_profile, x_hermes_profile, None, None
    )
    permission_manager = get_permission_manager_for_profile(profile)
    try:
        scope_enum = PermissionScope(scope)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid scope: {scope}")
    parts = grant_key.split(":")
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid grant_key format")
    try:
        risk_level = RL(parts[1])
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid risk_level: {parts[1]}")
    argument_pattern = parts[2] if len(parts) > 2 else None
    permission_manager.revoke(parts[0], scope_enum, risk_level, argument_pattern)
    return {"status": "revoked", "grant_key": grant_key}


@router.post("/confirmations/resolve")
async def resolve_confirmation(
    confirmation_id: str,
    choice: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    from core.security.confirmation import ConfirmationChoice, get_action_guard

    checker = PermissionChecker(key_info["permissions"])
    if not checker.can_execute():
        raise HTTPException(status_code=403, detail="Execute permission required")
    profile, _, _ = _ctx_from_headers(
        key_info, None, x_holix_profile, x_hermes_profile, None, None
    )
    guard = get_action_guard(profile)
    if guard is None:
        raise HTTPException(status_code=404, detail="No confirmation guard initialized")
    try:
        choice_enum = ConfirmationChoice(choice)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid choice: {choice}")
    success = guard.resolve_confirmation(confirmation_id, choice_enum)
    if not success:
        raise HTTPException(status_code=404, detail="Confirmation not found or already resolved")
    return {"status": "resolved", "confirmation_id": confirmation_id, "choice": choice}


@router.post("/plan/review")
async def resolve_plan_review(
    review_id: str,
    choice: str,
    feedback: str = "",
    key_info: dict = Depends(verify_api_key),
):
    from core.plan_review.review_guard import PlanReviewChoice, get_plan_review_guard

    checker = PermissionChecker(key_info["permissions"])
    if not checker.can_execute():
        raise HTTPException(status_code=403, detail="Execute permission required")
    guard = get_plan_review_guard()
    if guard is None:
        raise HTTPException(status_code=404, detail="No plan review guard initialized")
    try:
        choice_enum = PlanReviewChoice(choice)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid choice: {choice}")
    success = guard.resolve_review(review_id, choice_enum, feedback)
    if not success:
        raise HTTPException(status_code=404, detail="Review not found or already resolved")
    return {"status": "resolved", "review_id": review_id, "choice": choice, "feedback": feedback}


@router.get("/plans")
async def list_plans(limit: int = 20, key_info: dict = Depends(verify_api_key)):
    from core.plan_review.plan_storage import list_plans

    return {"plans": list_plans(limit=limit)}


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str, key_info: dict = Depends(verify_api_key)):
    from core.plan_review.plan_storage import (
        InvalidPlanIdError,
        get_plan_dir,
        load_plan,
        resolve_plan_path,
    )

    plan_dir = get_plan_dir()
    try:
        plan_path = resolve_plan_path(plan_dir, plan_id)
        return load_plan(str(plan_path))
    except InvalidPlanIdError:
        raise HTTPException(status_code=400, detail="Invalid plan id")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Plan not found")