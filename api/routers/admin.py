"""Admin API key and metrics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from api import state
from api.deps import verify_admin_key
from config import settings

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/api-keys")
async def create_api_key_endpoint(
    name: str,
    permissions: str = "read,write",
    rate_limit: int = 100,
    admin_key: dict = Depends(verify_admin_key),
):
    manager = state.api_key_manager
    if manager is None:
        raise HTTPException(status_code=503, detail="API key manager not initialized")
    api_key = await manager.create_api_key(name, permissions, rate_limit)
    return {
        "api_key": api_key,
        "name": name,
        "permissions": permissions,
        "rate_limit": rate_limit,
        "warning": "Save this API key securely. It will not be shown again!",
    }


@router.get("/api-keys")
async def list_api_keys_endpoint(admin_key: dict = Depends(verify_admin_key)):
    manager = state.api_key_manager
    if manager is None:
        raise HTTPException(status_code=503, detail="API key manager not initialized")
    keys = await manager.list_api_keys()
    return {"api_keys": keys, "count": len(keys)}


@router.delete("/api-keys/{key_id}")
async def revoke_api_key_endpoint(
    api_key_to_revoke: str,
    admin_key: dict = Depends(verify_admin_key),
):
    manager = state.api_key_manager
    if manager is None:
        raise HTTPException(status_code=503, detail="API key manager not initialized")
    success = await manager.revoke_api_key(api_key_to_revoke)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"success": True, "message": "API key revoked"}


@router.get("/metrics")
async def get_metrics(admin_key: dict = Depends(verify_admin_key)):
    from core.monitoring import metrics

    return {"metrics": metrics.get_metrics(), "summary": metrics.get_summary()}


@router.get("/metrics/prometheus", include_in_schema=False)
async def prometheus_metrics(admin_key: dict = Depends(verify_admin_key)):
    if not settings.enable_prometheus_metrics:
        raise HTTPException(status_code=404, detail="Metrics disabled")
    from core.monitoring import metrics as global_metrics

    from api.prometheus import format_prometheus

    return PlainTextResponse(
        format_prometheus(global_metrics),
        media_type="text/plain; version=0.0.4",
    )