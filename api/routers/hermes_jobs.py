"""Hermes-compatible /api/jobs (cron) endpoints."""

from __future__ import annotations

import asyncio

from core.cron import active_runs
from core.cron.store import CronStore
from fastapi import APIRouter, Depends, Header, HTTPException

from api import state
from api.deps import resolve_profile_name, verify_api_key
from api.schemas.hermes import JobCreateRequest, JobPatchRequest
from api.services.job_body import job_to_api_dict, normalize_job_fields

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_STORE_KEYS = frozenset({
    "task",
    "cron_expression",
    "name",
    "enabled",
    "notify_chat_id",
    "session_id",
    "skills",
    "model_override",
})


def _store_fields(fields: dict) -> dict:
    return {key: fields[key] for key in _STORE_KEYS if key in fields}


def _job_profile(
    x_helix_profile: str | None,
    x_hermes_profile: str | None,
) -> str:
    from api.deps import _header_alias

    return resolve_profile_name(
        header_profile=_header_alias(x_helix_profile, x_hermes_profile),
        model=None,
        host_profile=state.host_profile or "default",
    )


@router.get("")
async def list_jobs(
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    profile = _job_profile(x_helix_profile, x_hermes_profile)
    jobs = CronStore(profile).list_jobs()
    return {"jobs": [job_to_api_dict(j) for j in jobs], "count": len(jobs)}


@router.post("")
async def create_job(
    body: JobCreateRequest,
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    profile = _job_profile(x_helix_profile, x_hermes_profile)
    try:
        fields = normalize_job_fields(
            body.model_dump(exclude_none=True),
            require_task=True,
            require_schedule=True,
        )
        job = CronStore(profile).add(**_store_fields(fields))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return job_to_api_dict(job)


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    profile = _job_profile(x_helix_profile, x_hermes_profile)
    job = CronStore(profile).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_to_api_dict(job)


@router.patch("/{job_id}")
async def patch_job(
    job_id: str,
    body: JobPatchRequest,
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    profile = _job_profile(x_helix_profile, x_hermes_profile)
    store = CronStore(profile)
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        fields = normalize_job_fields(body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if "cron_expression" in fields and fields["cron_expression"]:
        from core.cron.expressions import validate_cron_expression

        fields["cron_expression"] = validate_cron_expression(fields["cron_expression"])
    for key, value in fields.items():
        setattr(job, key, value)
    try:
        updated = store.update(job)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found") from None
    return job_to_api_dict(updated)


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    profile = _job_profile(x_helix_profile, x_hermes_profile)
    store = CronStore(profile)
    active_runs.cancel(job_id)
    job = store.get(job_id)
    if job is not None and job.last_status == "running":
        job.last_status = "cancelled"
        job.last_error = None
        store.update(job)
    if not store.remove(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"deleted": True, "id": job_id, "cancelled": True}


@router.post("/{job_id}/pause")
async def pause_job(
    job_id: str,
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    profile = _job_profile(x_helix_profile, x_hermes_profile)
    try:
        job = CronStore(profile).set_enabled(job_id, False)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found") from None
    return job_to_api_dict(job)


@router.post("/{job_id}/resume")
async def resume_job(
    job_id: str,
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    profile = _job_profile(x_helix_profile, x_hermes_profile)
    try:
        job = CronStore(profile).set_enabled(job_id, True)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found") from None
    return job_to_api_dict(job)


@router.post("/{job_id}/run")
async def run_job_now(
    job_id: str,
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    profile = _job_profile(x_helix_profile, x_hermes_profile)
    store = CronStore(profile)
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if active_runs.is_active(job_id) or job.last_status == "running":
        raise HTTPException(status_code=409, detail="Job is already running")

    from core.cron.runner import run_cron_job

    task = asyncio.create_task(run_cron_job(job), name=f"cron-manual-{job_id}")
    active_runs.register_task(job_id, task)
    try:
        await task
    except asyncio.CancelledError:
        refreshed = store.get(job_id)
        return {
            "status": "cancelled",
            "job_id": job_id,
            "last_status": refreshed.last_status if refreshed else "cancelled",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    refreshed = store.get(job_id)
    return {
        "status": "completed",
        "job_id": job_id,
        "last_status": refreshed.last_status if refreshed else None,
    }