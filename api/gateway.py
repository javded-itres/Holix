import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime

from core.agent import HelixAgent
from core.agent_events import create_compatibility_print_handler
from core.di.container import (
    create_async_container,
    get_agent_from_container,
    resolve_gateway_runtime_config,
)
from core.loop_streaming import StreamingAgentLoop
from core.security.auth import APIKeyManager, RateLimiter
from core.security.permissions import PermissionChecker
from dishka.integrations.fastapi import setup_dishka
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse

import api.deps as gateway_deps
from api.deps import verify_admin_key, verify_api_key
from api.docs_chat import router as docs_chat_router
from api.models import ChatCompletionRequest, ChatCompletionResponse
from config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize Dishka container, agent, and API key store."""
    global agent, api_key_manager

    if settings.is_production and not settings.api_key_pepper.strip():
        raise RuntimeError(
            "HELIX_API_KEY_PEPPER is required when HELIX_ENV=production"
        )

    compat_handler = create_compatibility_print_handler()
    agent = await get_agent_from_container(app.state.dishka_container)
    agent.events.subscribe(compat_handler)

    api_key_manager = APIKeyManager(settings.api_keys_db_path)
    await api_key_manager.initialize_db()
    gateway_deps.api_key_manager = api_key_manager
    gateway_deps.rate_limiter = rate_limiter

    yield

    await app.state.dishka_container.close()


app = FastAPI(
    title="Helix API",
    description="Self-improving AI agent with memory and skills",
    version="0.1.0",
    lifespan=lifespan,
)

_origins = settings.cors_origin_list()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent: HelixAgent | None = None
api_key_manager: APIKeyManager | None = None
rate_limiter = RateLimiter()
_agent_request_lock = asyncio.Lock()

_dishka_container = create_async_container(resolve_gateway_runtime_config())
setup_dishka(container=_dishka_container, app=app)
app.include_router(docs_chat_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Helix API",
        "version": "0.1.0",
        "status": "running",
        "agent_initialized": agent is not None and agent._initialized
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "agent_ready": agent is not None and agent._initialized,
        "require_auth": settings.effective_require_auth,
    }


@app.get("/metrics")
async def prometheus_metrics(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None),
):
    """Prometheus metrics. Requires admin key in production."""
    if not settings.enable_prometheus_metrics:
        raise HTTPException(status_code=404, detail="Metrics disabled")
    if settings.is_production:
        await verify_admin_key(authorization=authorization, x_api_key=x_api_key)

    from core.monitoring import metrics as global_metrics

    from api.prometheus import format_prometheus

    return PlainTextResponse(
        format_prometheus(global_metrics),
        media_type="text/plain; version=0.0.4",
    )


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest,
    key_info: dict | None = Depends(verify_api_key)
):
    """OpenAI-compatible chat completions endpoint.

    Args:
        request: Chat completion request
        key_info: API key info (if auth enabled)

    Returns:
        Chat completion response
    """
    if agent is None or not agent._initialized:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    # Check permissions
    if key_info:
        checker = PermissionChecker(key_info["permissions"])
        if not checker.can_read():
            raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Extract the last user message
    user_messages = [msg for msg in request.messages if msg.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")

    user_input = user_messages[-1].content

    # Check if streaming is requested
    if request.stream:
        streaming_loop = StreamingAgentLoop(agent)

        async def generate():
            async with _agent_request_lock:
                async for chunk in streaming_loop.run_conversation_stream(
                    user_input=user_input,
                    conversation_id=request.conversation_id,
                ):
                    yield chunk

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    # Non-streaming response
    try:
        start_time = time.time()
        async with _agent_request_lock:
            response = await agent.run(
                user_input=user_input,
                conversation_id=request.conversation_id,
            )
        elapsed_time = time.time() - start_time

        # Build OpenAI-compatible response
        return ChatCompletionResponse(
            id=f"chatcmpl-{int(time.time())}",
            object="chat.completion",
            created=int(time.time()),
            model=request.model,
            choices=[
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response
                    },
                    "finish_reason": "stop"
                }
            ],
            usage={
                "prompt_tokens": 0,  # Not tracked yet
                "completion_tokens": 0,
                "total_tokens": 0,
                "elapsed_seconds": round(elapsed_time, 2)
            }
        )

    except Exception as e:
        from api.errors import agent_error_to_http

        raise agent_error_to_http(e) from e


@app.get("/v1/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    limit: int = 30,
    key_info: dict | None = Depends(verify_api_key)
):
    """Get conversation history.

    Args:
        conversation_id: Conversation ID
        limit: Maximum number of messages
        key_info: API key info (if auth enabled)

    Returns:
        Conversation history
    """
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    history = await agent.get_conversation_history(conversation_id, limit)

    return {
        "conversation_id": conversation_id,
        "messages": history,
        "count": len(history)
    }


@app.get("/v1/skills")
async def list_skills(key_info: dict | None = Depends(verify_api_key)):
    """List all available skills.

    Returns:
        Dictionary of skills
    """
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    skills = agent.get_skills()

    return {
        "skills": skills,
        "count": len(skills)
    }


@app.get("/v1/tools")
async def list_tools(key_info: dict | None = Depends(verify_api_key)):
    """List all available tools.

    Returns:
        List of tool names
    """
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    tools = agent.get_tools()

    return {
        "tools": tools,
        "count": len(tools)
    }


@app.post("/v1/search")
async def search_memory(
    query: str,
    top_k: int = 5,
    key_info: dict | None = Depends(verify_api_key),
):
    """Search through agent memory.

    Args:
        query: Search query
        top_k: Number of results

    Returns:
        Search results
    """
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    results = await agent.search_memory(query, top_k)

    return {
        "query": query,
        "results": results,
        "count": len(results)
    }


# API Key Management Endpoints
@app.post("/admin/api-keys")
async def create_api_key_endpoint(
    name: str,
    permissions: str = "read,write",
    rate_limit: int = 100,
    admin_key: dict = Depends(verify_admin_key)
):
    """Create a new API key (admin only).

    Args:
        name: Key name/description
        permissions: Comma-separated permissions
        rate_limit: Requests per minute
        admin_key: Admin API key

    Returns:
        New API key (save this!)
    """
    api_key = await api_key_manager.create_api_key(name, permissions, rate_limit)

    return {
        "api_key": api_key,
        "name": name,
        "permissions": permissions,
        "rate_limit": rate_limit,
        "warning": "Save this API key securely. It will not be shown again!"
    }


@app.get("/admin/api-keys")
async def list_api_keys_endpoint(
    admin_key: dict = Depends(verify_admin_key)
):
    """List all API keys (admin only).

    Args:
        admin_key: Admin API key

    Returns:
        List of API keys
    """
    keys = await api_key_manager.list_api_keys()

    return {
        "api_keys": keys,
        "count": len(keys)
    }


@app.delete("/admin/api-keys/{key_id}")
async def revoke_api_key_endpoint(
    api_key_to_revoke: str,
    admin_key: dict = Depends(verify_admin_key)
):
    """Revoke an API key (admin only).

    Args:
        api_key_to_revoke: API key to revoke
        admin_key: Admin API key

    Returns:
        Success status
    """
    success = await api_key_manager.revoke_api_key(api_key_to_revoke)

    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    return {"success": True, "message": "API key revoked"}


@app.get("/admin/metrics")
async def get_metrics(admin_key: dict = Depends(verify_admin_key)):
    """Get system metrics (admin only).

    Args:
        admin_key: Admin API key

    Returns:
        System metrics
    """
    from core.monitoring import metrics

    return {
        "metrics": metrics.get_metrics(),
        "summary": metrics.get_summary()
    }


# ─── Permission Management Endpoints ────────────────────────────────────────

@app.post("/v1/permissions/grant")
async def grant_permission(
    tool_name: str,
    risk_level: str = "high",
    scope: str = "session",
    argument_pattern: str | None = None,
    key_info: dict | None = Depends(verify_api_key),
):
    """Pre-authorize a tool for subsequent calls.

    API users call this before running the agent to avoid
    confirmation-denied errors during execution.

    Args:
        tool_name: Name of the tool to authorize (e.g., "run_terminal_command").
        risk_level: Risk level to authorize ("no", "low", "medium", "high").
        scope: How long the grant lasts ("session" or "always").
        argument_pattern: Optional specific pattern to match.
        key_info: API key info (if auth is enabled).
    """
    from core.security.confirmation import PermissionScope, permission_manager
    from core.security.confirmation import RiskLevel as RL

    if key_info:
        checker = PermissionChecker(key_info["permissions"])
        if not checker.can_execute():
            raise HTTPException(status_code=403, detail="Execute permission required")

    try:
        risk_enum = RL(risk_level)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid risk_level: {risk_level}. Must be one of: no, low, medium, high")

    try:
        scope_enum = PermissionScope(scope)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid scope: {scope}. Must be one of: session, always")

    permission_manager.grant(tool_name, scope_enum, risk_enum, argument_pattern)

    return {
        "status": "granted",
        "tool_name": tool_name,
        "scope": scope,
        "risk_level": risk_level,
    }


@app.get("/v1/permissions")
async def list_permissions(key_info: dict | None = Depends(verify_api_key)):
    """List all active permission grants."""
    from core.security.confirmation import permission_manager


    return permission_manager.list_grants()


@app.delete("/v1/permissions/{grant_key}")
async def revoke_permission(
    grant_key: str,
    scope: str = "always",
    key_info: dict | None = Depends(verify_api_key),
):
    """Revoke a permission grant."""
    from core.security.confirmation import PermissionScope, permission_manager


    try:
        scope_enum = PermissionScope(scope)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid scope: {scope}")

    # Parse the grant_key (format: "tool_name:risk_level" or "tool_name:risk_level:pattern")
    parts = grant_key.split(":")
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid grant_key format. Use 'tool:risk_level' or 'tool:risk_level:pattern'")

    from core.security.confirmation import RiskLevel as RL
    tool_name = parts[0]
    try:
        risk_level = RL(parts[1])
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid risk_level: {parts[1]}")

    argument_pattern = parts[2] if len(parts) > 2 else None
    permission_manager.revoke(tool_name, scope_enum, risk_level, argument_pattern)

    return {"status": "revoked", "grant_key": grant_key}


# ─── Confirmation Endpoints ────────────────────────────────────────────────

@app.post("/v1/confirmations/resolve")
async def resolve_confirmation(
    confirmation_id: str,
    choice: str,
    key_info: dict | None = Depends(verify_api_key),
):
    """Resolve a pending dangerous-action confirmation (same guard as TUI).

    Args:
        confirmation_id: ID from ConfirmationRequestEvent.
        choice: One of allow_once, allow_session, allow_always, deny.
    """
    from core.security.confirmation import ConfirmationChoice, get_action_guard

    if key_info:
        checker = PermissionChecker(key_info["permissions"])
        if not checker.can_execute():
            raise HTTPException(status_code=403, detail="Execute permission required")

    guard = get_action_guard()
    if guard is None:
        raise HTTPException(status_code=404, detail="No confirmation guard initialized")

    try:
        choice_enum = ConfirmationChoice(choice)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": f"Invalid choice: {choice}",
                    "type": "invalid_request_error",
                    "code": "invalid_confirmation_choice",
                }
            },
        )

    success = guard.resolve_confirmation(confirmation_id, choice_enum)
    if not success:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "message": f"Confirmation {confirmation_id} not found or already resolved",
                    "type": "invalid_request_error",
                    "code": "confirmation_not_found",
                }
            },
        )

    return {
        "status": "resolved",
        "confirmation_id": confirmation_id,
        "choice": choice,
    }


# ─── Plan Review Endpoints ─────────────────────────────────────────────────

@app.post("/v1/plan/review")
async def resolve_plan_review(
    review_id: str,
    choice: str,
    feedback: str = "",
    key_info: dict | None = Depends(verify_api_key),
):
    """Resolve a pending plan review request.

    API clients call this when using plan_and_execute or hybrid mode
    to approve, auto-execute, refine, or reject a generated plan.

    Args:
        review_id: The ID from PlanReviewRequestEvent.
        choice: One of "confirm_step", "auto_execute", "refine", "reject".
        feedback: Optional refinement feedback (used when choice is "refine").
        key_info: API key info (if auth is enabled).
    """
    from core.plan_review.review_guard import PlanReviewChoice, get_plan_review_guard

    if key_info:
        checker = PermissionChecker(key_info["permissions"])
        if not checker.can_execute():
            raise HTTPException(status_code=403, detail="Execute permission required")

    guard = get_plan_review_guard()
    if guard is None:
        raise HTTPException(status_code=404, detail="No plan review guard initialized")

    try:
        choice_enum = PlanReviewChoice(choice)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid choice: {choice}. Must be one of: confirm_step, auto_execute, refine, reject",
        )

    success = guard.resolve_review(review_id, choice_enum, feedback)

    if not success:
        raise HTTPException(status_code=404, detail=f"Review {review_id} not found or already resolved")

    return {
        "status": "resolved",
        "review_id": review_id,
        "choice": choice,
        "feedback": feedback,
    }


@app.get("/v1/plans")
async def list_plans(limit: int = 20, key_info: dict | None = Depends(verify_api_key)):
    """List all saved execution plans.

    Args:
        limit: Maximum number of plans to return.
        key_info: API key info (if auth is enabled).
    """
    from core.plan_review.plan_storage import list_plans


    return {"plans": list_plans(limit=limit)}


@app.get("/v1/plans/{plan_id}")
async def get_plan(plan_id: str, key_info: dict | None = Depends(verify_api_key)):
    """Get a specific plan by its path.

    Args:
        plan_id: The plan file name (e.g., "20260603_143000_default.json").
        key_info: API key info (if auth is enabled).
    """
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
