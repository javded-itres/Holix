"""Gateway enforces API key on protected routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_health_public_without_key() -> None:
    import api.gateway

    client = TestClient(api.gateway.app)
    assert client.get("/health").status_code == 200
    assert client.get("/v1/health").status_code == 200


def test_protected_route_requires_key() -> None:
    import api.gateway

    client = TestClient(api.gateway.app)
    response = client.get("/v1/models")
    assert response.status_code == 401


def test_protected_route_accepts_key(gateway_client: TestClient, gateway_auth_headers: dict) -> None:
    response = gateway_client.get("/v1/models", headers=gateway_auth_headers)
    assert response.status_code == 200
    assert response.json()["object"] == "list"