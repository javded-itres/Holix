"""Cross-profile access must be denied on gateway resource routes."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _profile_headers(profile: str, base: dict[str, str]) -> dict[str, str]:
    return {**base, "X-Holix-Profile": profile}


def test_session_idor_blocked(gateway_client: TestClient, gateway_auth_headers: dict) -> None:
    created = gateway_client.post(
        "/api/sessions",
        headers=_profile_headers("alice", gateway_auth_headers),
        json={"title": "alice session"},
    )
    assert created.status_code == 200
    sid = created.json()["id"]
    assert created.json()["profile"] == "alice"

    denied = gateway_client.get(
        f"/api/sessions/{sid}",
        headers=_profile_headers("bob", gateway_auth_headers),
    )
    assert denied.status_code == 404

    allowed = gateway_client.get(
        f"/api/sessions/{sid}",
        headers=_profile_headers("alice", gateway_auth_headers),
    )
    assert allowed.status_code == 200


def test_response_idor_blocked(gateway_client: TestClient, gateway_auth_headers: dict) -> None:
    import api.state

    store = api.state.responses_store
    assert store is not None
    stored = store.save(
        profile="alice",
        payload={"object": "response", "status": "completed", "output": []},
        conversation="conv-alice",
    )

    denied = gateway_client.get(
        f"/v1/responses/{stored.id}",
        headers=_profile_headers("bob", gateway_auth_headers),
    )
    assert denied.status_code == 404

    allowed = gateway_client.get(
        f"/v1/responses/{stored.id}",
        headers=_profile_headers("alice", gateway_auth_headers),
    )
    assert allowed.status_code == 200


def test_run_idor_blocked(gateway_client: TestClient, gateway_auth_headers: dict) -> None:
    import api.state

    runs = api.state.runs_store
    assert runs is not None
    record = runs.create(profile="alice", model="alice", input_text="secret")

    denied = gateway_client.get(
        f"/v1/runs/{record.run_id}",
        headers=_profile_headers("bob", gateway_auth_headers),
    )
    assert denied.status_code == 404

    allowed = gateway_client.get(
        f"/v1/runs/{record.run_id}",
        headers=_profile_headers("alice", gateway_auth_headers),
    )
    assert allowed.status_code == 200