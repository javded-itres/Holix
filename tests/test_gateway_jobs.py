"""Hermes-compatible /api/jobs gateway tests."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def holix_home(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def jobs_client(
    gateway_client: TestClient,
    gateway_auth_headers: dict,
    holix_home,
    monkeypatch: pytest.MonkeyPatch,
):
    async def _fast_run(job):
        await asyncio.sleep(0)
        from core.cron.store import CronStore

        store = CronStore(job.profile)
        current = store.get(job.id)
        if current is None:
            return
        current.last_status = "success"
        store.update(current)

    monkeypatch.setattr("core.cron.runner.run_cron_job", _fast_run)
    return gateway_client, gateway_auth_headers


def test_jobs_hermes_schema_create_and_list(jobs_client) -> None:
    client, headers = jobs_client
    created = client.post(
        "/api/jobs",
        headers=headers,
        json={
            "prompt": "Daily summary",
            "schedule": "every day at 9",
            "name": "morning",
            "skills": ["github-pr-workflow"],
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["prompt"] == "Daily summary"
    assert body["schedule"] == body["cron_expression"]
    assert body["skills"] == ["github-pr-workflow"]

    listed = client.get("/api/jobs", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["count"] == 1


def test_jobs_lifecycle(jobs_client) -> None:
    client, headers = jobs_client
    created = client.post(
        "/api/jobs",
        headers=headers,
        json={"task": "ping", "cron_expression": "0 9 * * *", "name": "ping"},
    )
    job_id = created.json()["id"]

    paused = client.post(f"/api/jobs/{job_id}/pause", headers=headers)
    assert paused.status_code == 200
    assert paused.json()["enabled"] is False

    resumed = client.post(f"/api/jobs/{job_id}/resume", headers=headers)
    assert resumed.status_code == 200
    assert resumed.json()["enabled"] is True

    patched = client.patch(
        f"/api/jobs/{job_id}",
        headers=headers,
        json={"schedule": "hourly"},
    )
    assert patched.status_code == 200
    assert patched.json()["cron_expression"] == "0 * * * *"

    ran = client.post(f"/api/jobs/{job_id}/run", headers=headers)
    assert ran.status_code == 200
    assert ran.json()["status"] == "completed"

    deleted = client.delete(f"/api/jobs/{job_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


def test_jobs_invalid_schedule(jobs_client) -> None:
    client, headers = jobs_client
    response = client.post(
        "/api/jobs",
        headers=headers,
        json={"prompt": "x", "schedule": "not a real schedule"},
    )
    assert response.status_code == 400