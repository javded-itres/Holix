"""Documentation-site chat API (restricted, no agent tools)."""

from __future__ import annotations

import time

from core.docs_chat.service import DocsChatService
from core.docs_chat.sessions import clear_session, load_session, validate_client_id
from core.security.auth import RateLimiter
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import settings

router = APIRouter(prefix="/v1/docs/chat", tags=["docs-chat"])

_docs_rate_limiter = RateLimiter()
_service: DocsChatService | None = None


class DocsChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    client_id: str = Field(..., min_length=8, max_length=64)
    lang: str = Field(default="ru", pattern=r"^(en|ru)$")
    page_slug: str | None = Field(default=None, max_length=64)
    stream: bool = True


class DocsChatConfigResponse(BaseModel):
    enabled: bool
    proxy_path: str = "/api/docs-chat"
    session_path: str = "/api/docs-chat/session"


def _get_service() -> DocsChatService:
    global _service
    if _service is None:
        _service = DocsChatService()
    return _service


def _verify_docs_chat_token(
    authorization: str | None,
    x_docs_chat_token: str | None,
) -> None:
    expected = settings.docs_chat_token.strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Docs chat is not configured")
    token: str | None = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif x_docs_chat_token:
        token = x_docs_chat_token.strip()
    if not token or token != expected:
        raise HTTPException(status_code=401, detail="Invalid docs chat token")


def _rate_limit_client(client_id: str) -> None:
    try:
        cid = validate_client_id(client_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid client_id") from exc
    if not _docs_rate_limiter.check_rate_limit(
        f"docs-chat-client:{cid}",
        settings.docs_chat_rate_limit_rpm,
    ):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")


@router.get("/config", response_model=DocsChatConfigResponse)
async def docs_chat_config() -> DocsChatConfigResponse:
    """Public config for the website widget (no secrets)."""
    return DocsChatConfigResponse(enabled=settings.docs_chat_enabled)


@router.get("/session")
async def docs_chat_get_session(
    client_id: str = Query(..., min_length=8, max_length=64),
    authorization: str | None = Header(None),
    x_docs_chat_token: str | None = Header(None, alias="X-Docs-Chat-Token"),
):
    """Load saved chat history for an anonymous visitor."""
    if not settings.docs_chat_enabled:
        raise HTTPException(status_code=404, detail="Docs chat disabled")
    _verify_docs_chat_token(authorization, x_docs_chat_token)
    _rate_limit_client(client_id)
    try:
        return load_session(client_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid client_id") from exc


@router.delete("/session")
async def docs_chat_clear_session(
    client_id: str = Query(..., min_length=8, max_length=64),
    authorization: str | None = Header(None),
    x_docs_chat_token: str | None = Header(None, alias="X-Docs-Chat-Token"),
):
    """Clear chat history for an anonymous visitor."""
    if not settings.docs_chat_enabled:
        raise HTTPException(status_code=404, detail="Docs chat disabled")
    _verify_docs_chat_token(authorization, x_docs_chat_token)
    try:
        clear_session(client_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid client_id") from exc
    return {"ok": True}


@router.post("")
async def docs_chat(
    request: DocsChatRequest,
    authorization: str | None = Header(None),
    x_docs_chat_token: str | None = Header(None, alias="X-Docs-Chat-Token"),
):
    """Answer questions about Holix documentation — no tools, no commands."""
    if not settings.docs_chat_enabled:
        raise HTTPException(status_code=404, detail="Docs chat disabled")
    _verify_docs_chat_token(authorization, x_docs_chat_token)
    _rate_limit_client(request.client_id)
    service = _get_service()
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Empty message")

    try:
        validate_client_id(request.client_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid client_id") from exc

    if request.stream:

        async def generate():
            async for chunk in service.stream(
                message,
                lang=request.lang,
                page_slug=request.page_slug,
                client_id=request.client_id,
            ):
                yield chunk

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    content, pages, open_slug = await service.complete(
        message,
        lang=request.lang,
        page_slug=request.page_slug,
        client_id=request.client_id,
    )
    return {
        "id": f"docschat-{int(time.time())}",
        "object": "docs.chat.completion",
        "created": int(time.time()),
        "content": content,
        "pages": pages,
        "open_slug": open_slug,
    }