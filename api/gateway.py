from typing import Optional
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from datetime import datetime
import time

from api.models import ChatCompletionRequest, ChatCompletionResponse
from core.agent import HelixAgent
from core.loop_streaming import StreamingAgentLoop
from core.security.auth import APIKeyManager, RateLimiter
from core.security.permissions import PermissionChecker, Permission

app = FastAPI(
    title="Helix API",
    description="Self-improving AI agent with memory and skills",
    version="0.1.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
agent: Optional[HelixAgent] = None
api_key_manager: Optional[APIKeyManager] = None
rate_limiter = RateLimiter()

# Configuration
REQUIRE_AUTH = False  # Set to True to enable authentication


@app.on_event("startup")
async def startup_event():
    """Initialize the agent on startup."""
    global agent, api_key_manager
    agent = HelixAgent()
    await agent.initialize()

    # Initialize API key manager
    api_key_manager = APIKeyManager()
    await api_key_manager.initialize_db()


async def verify_api_key(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None)
) -> Optional[dict]:
    """Verify API key from headers.

    Args:
        authorization: Authorization header (Bearer token)
        x_api_key: X-API-Key header

    Returns:
        API key info if valid

    Raises:
        HTTPException: If authentication is required and key is invalid
    """
    if not REQUIRE_AUTH:
        return None  # Auth disabled

    # Extract API key
    api_key = None
    if authorization and authorization.startswith("Bearer "):
        api_key = authorization[7:]
    elif x_api_key:
        api_key = x_api_key

    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    # Validate key
    key_info = await api_key_manager.validate_api_key(api_key)
    if not key_info:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Check rate limit
    key_hash = api_key_manager.hash_key(api_key)
    if not rate_limiter.check_rate_limit(key_hash, key_info["rate_limit"]):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return key_info


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
        "agent_ready": agent is not None and agent._initialized
    }


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest,
    key_info: Optional[dict] = Depends(verify_api_key)
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
        # Return streaming response
        streaming_loop = StreamingAgentLoop(agent)

        async def generate():
            async for chunk in streaming_loop.run_conversation_stream(
                user_input=user_input,
                conversation_id=request.conversation_id
            ):
                yield chunk

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )

    # Non-streaming response
    try:
        start_time = time.time()
        response = await agent.run(
            user_input=user_input,
            conversation_id=request.conversation_id
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
        raise HTTPException(status_code=500, detail=f"Error running agent: {str(e)}")


@app.get("/v1/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    limit: int = 30,
    key_info: Optional[dict] = Depends(verify_api_key)
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
async def list_skills():
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
async def list_tools():
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
async def search_memory(query: str, top_k: int = 5):
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
    admin_key: Optional[dict] = Depends(verify_api_key)
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
    if REQUIRE_AUTH:
        if not admin_key:
            raise HTTPException(status_code=401, detail="Admin authentication required")

        checker = PermissionChecker(admin_key["permissions"])
        if not checker.is_admin():
            raise HTTPException(status_code=403, detail="Admin permission required")

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
    admin_key: Optional[dict] = Depends(verify_api_key)
):
    """List all API keys (admin only).

    Args:
        admin_key: Admin API key

    Returns:
        List of API keys
    """
    if REQUIRE_AUTH:
        if not admin_key:
            raise HTTPException(status_code=401, detail="Admin authentication required")

        checker = PermissionChecker(admin_key["permissions"])
        if not checker.is_admin():
            raise HTTPException(status_code=403, detail="Admin permission required")

    keys = await api_key_manager.list_api_keys()

    return {
        "api_keys": keys,
        "count": len(keys)
    }


@app.delete("/admin/api-keys/{key_id}")
async def revoke_api_key_endpoint(
    api_key_to_revoke: str,
    admin_key: Optional[dict] = Depends(verify_api_key)
):
    """Revoke an API key (admin only).

    Args:
        api_key_to_revoke: API key to revoke
        admin_key: Admin API key

    Returns:
        Success status
    """
    if REQUIRE_AUTH:
        if not admin_key:
            raise HTTPException(status_code=401, detail="Admin authentication required")

        checker = PermissionChecker(admin_key["permissions"])
        if not checker.is_admin():
            raise HTTPException(status_code=403, detail="Admin permission required")

    success = await api_key_manager.revoke_api_key(api_key_to_revoke)

    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    return {"success": True, "message": "API key revoked"}


@app.get("/admin/metrics")
async def get_metrics(admin_key: Optional[dict] = Depends(verify_api_key)):
    """Get system metrics (admin only).

    Args:
        admin_key: Admin API key

    Returns:
        System metrics
    """
    if REQUIRE_AUTH:
        if not admin_key:
            raise HTTPException(status_code=401, detail="Admin authentication required")

        checker = PermissionChecker(admin_key["permissions"])
        if not checker.is_admin():
            raise HTTPException(status_code=403, detail="Admin permission required")

    from core.monitoring import metrics

    return {
        "metrics": metrics.get_metrics(),
        "summary": metrics.get_summary()
    }
