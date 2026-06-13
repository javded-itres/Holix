"""Hermes-compatible /v1/runs polling and terminal statuses."""

from __future__ import annotations

from core.gateway.run_poll import is_terminal_run_status, poll_run
from fastapi.testclient import TestClient


def test_is_terminal_run_status_accepts_completed_and_done() -> None:
    assert is_terminal_run_status("completed")
    assert is_terminal_run_status("done")
    assert is_terminal_run_status("failed")
    assert is_terminal_run_status("cancelled")
    assert not is_terminal_run_status("running")
    assert not is_terminal_run_status("started")


def test_runs_poll_returns_completed_with_last_event(
    gateway_client: TestClient,
    gateway_auth_headers: dict,
) -> None:
    created = gateway_client.post(
        "/v1/runs",
        headers=gateway_auth_headers,
        json={"input": "ping", "model": "default"},
    )
    assert created.status_code == 202
    run_id = created.json()["run_id"]

    result = poll_run(
        lambda rid: gateway_client.get(
            f"/v1/runs/{rid}",
            headers=gateway_auth_headers,
        ).json(),
        run_id,
        timeout=5.0,
        interval=0.05,
    )
    assert result["status"] == "completed"
    assert result["last_event"] == "run.completed"
    assert result["completed"] is True
    assert result["output"] == "ok"


def test_runs_reject_empty_input(
    gateway_client: TestClient,
    gateway_auth_headers: dict,
) -> None:
    response = gateway_client.post(
        "/v1/runs",
        headers=gateway_auth_headers,
        json={"input": "   ", "model": "default"},
    )
    assert response.status_code == 400