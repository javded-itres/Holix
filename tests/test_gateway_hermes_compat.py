"""Hermes-compatible gateway endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_capabilities(gateway_client: TestClient, gateway_auth_headers: dict) -> None:
    response = gateway_client.get("/v1/capabilities", headers=gateway_auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "holix.api_server.capabilities"
    assert data["features"]["chat_completions"] is True
    assert data["features"]["responses_api"] is True
    assert data["features"]["jobs_hermes_schema"] is True
    assert data["features"]["multimodal_input"] is True
    assert data["session_id_header"] == "X-Holix-Session-Id"


def test_toolsets(gateway_client: TestClient, gateway_auth_headers: dict) -> None:
    response = gateway_client.get("/v1/toolsets", headers=gateway_auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body[0]["name"] == "core"
    assert "read_file" in body[0]["tools"]


def test_sessions_crud(gateway_client: TestClient, gateway_auth_headers: dict) -> None:
    created = gateway_client.post(
        "/api/sessions",
        headers=gateway_auth_headers,
        json={"title": "test session"},
    )
    assert created.status_code == 200
    sid = created.json()["id"]

    listed = gateway_client.get("/api/sessions", headers=gateway_auth_headers)
    assert listed.status_code == 200
    assert listed.json()["count"] >= 1

    detail = gateway_client.get(f"/api/sessions/{sid}", headers=gateway_auth_headers)
    assert detail.status_code == 200

    chat = gateway_client.post(
        f"/api/sessions/{sid}/chat",
        headers=gateway_auth_headers,
        json={"input": "hello"},
    )
    assert chat.status_code == 200
    assert chat.json()["output"] == "ok"


def test_sessions_source_filter(gateway_client: TestClient, gateway_auth_headers: dict) -> None:
    gateway_client.post(
        "/api/sessions",
        headers=gateway_auth_headers,
        json={"title": "api session", "source": "api"},
    )
    listed = gateway_client.get(
        "/api/sessions?source=api&include_children=false",
        headers=gateway_auth_headers,
    )
    assert listed.status_code == 200
    assert listed.json()["count"] >= 1
    assert all(s["source"] == "api" for s in listed.json()["sessions"])


def test_multimodal_rejects_file_upload(
    gateway_client: TestClient,
    gateway_auth_headers: dict,
) -> None:
    response = gateway_client.post(
        "/v1/chat/completions",
        headers=gateway_auth_headers,
        json={
            "model": "default",
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "file", "file_id": "file-abc"}],
                }
            ],
        },
    )
    assert response.status_code == 400
    assert "unsupported_content_type" in response.json()["detail"]


def test_runs_lifecycle(gateway_client: TestClient, gateway_auth_headers: dict) -> None:
    created = gateway_client.post(
        "/v1/runs",
        headers=gateway_auth_headers,
        json={"input": "ping", "model": "default"},
    )
    assert created.status_code == 200
    run_id = created.json()["run_id"]

    import time

    for _ in range(20):
        status = gateway_client.get(f"/v1/runs/{run_id}", headers=gateway_auth_headers)
        if status.json().get("status") == "completed":
            break
        time.sleep(0.1)
    assert status.status_code == 200
    assert status.json()["status"] == "completed"