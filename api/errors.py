"""OpenAI-compatible error mapping for the API gateway."""

from __future__ import annotations

from fastapi import HTTPException


def openai_error_body(
    message: str,
    *,
    error_type: str = "server_error",
    code: str = "internal_error",
) -> dict:
    return {
        "error": {
            "message": message,
            "type": error_type,
            "code": code,
        }
    }


def agent_error_to_http(exc: Exception, *, default_status: int = 500) -> HTTPException:
    """Map agent/runtime exceptions to OpenAI-style HTTPException detail."""
    if isinstance(exc, HTTPException):
        return exc

    message = str(exc) or "Unknown error"
    lower = message.lower()
    status = default_status
    error_type = "server_error"
    code = "internal_error"

    if "not initialized" in lower or "not ready" in lower:
        status = 503
        error_type = "service_unavailable"
        code = "agent_unavailable"
    elif "permission" in lower or "forbidden" in lower:
        status = 403
        error_type = "permission_denied"
        code = "insufficient_permissions"
    elif "confirmation" in lower or "denied" in lower:
        status = 409
        error_type = "confirmation_required"
        code = "confirmation_denied"
    elif "plan review" in lower or "review" in lower and "not found" in lower:
        status = 404
        error_type = "invalid_request_error"
        code = "plan_review_not_found"
    elif "timeout" in lower:
        status = 504
        error_type = "timeout"
        code = "gateway_timeout"

    return HTTPException(
        status_code=status,
        detail=openai_error_body(message, error_type=error_type, code=code),
    )