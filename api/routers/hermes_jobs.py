"""Hermes-compatible /api/jobs (cron) endpoints."""

from __future__ import annotations

from core.cron.models import CronJob
from core.cron.store import CronStore
from fastapi import APIRouter, Depends, Header, HTTPException

from api import state
from api.deps import resolve_profile_name, verify_api_key
from api.schemas.hermes import JobCreateRequest, JobPatchRequest

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


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


def _job_to_dict(job: CronJob) -> dict:
    return job.model_dump()


@router.get("")
async def list_jobs(
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    profile = _job_profile(x_helix_profile, x_hermes_profile)
    jobs = CronStore(profile).list_jobs()
    return {"jobs": [_job_to_dict(j) for j in jobs], "count": len(jobs)}


@router.post("")
async def create_job(
    body: JobCreateRequest,
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    profile = _job_profile(x_helix_profile, x_hermes_profile)
    try:
        job = CronStore(profile).add(
            task=body.task,
            cron_expression=body.cron_expression,
            name=body.name,
            enabled=body.enabled,
            notify_chat_id=body.notify_chat_id,
            session_id=body.session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _job_to_dict(job)


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
    return _job_to_dict(job)


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
    data = body.model_dump(exclude_unset=True)
    if "cron_expression" in data and data["cron_expression"]:
        from core.cron.expressions import validate_cron_expression

        data["cron_expression"] = validate_cron_expression(data["cron_expression"])
    for key, value in data.items():
        setattr(job, key, value)
    try:
        updated = store.update(job)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found") from None
    return _job_to_dict(updated)


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_hermes_profile: str | None = Header(None),
):
    profile = _job_profile(x_helix_profile, x_hermes_profile)
    if not CronStore(profile).remove(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"deleted": True, "id": job_id}


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
    return _job_to_dict(job)


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
    return _job_to_dict(job)


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
    from core.cron.runner import run_cron_job

    try:
        await run_cron_job(job)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    refreshed = store.get(job_id)
    return {
        "status": "completed",
        "job_id": job_id,
        "last_status": refreshed.last_status if refreshed else None,
    }