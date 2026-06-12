"""Gateway enforces API key on protected routes."""

from __future__ import annotations

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


def test_protected_route_accepts_x_api_key_header(gateway_client: TestClient) -> None:
    response = gateway_client.get("/v1/models", headers={"X-API-Key": "test-key"})
    assert response.status_code == 200
    assert response.json()["object"] == "list"


def test_openapi_uses_single_authorize_scheme() -> None:
    import api.gateway

    schema = api.gateway.app.openapi()
    security_schemes = schema["components"]["securitySchemes"]
    assert "HolixApiKey" in security_schemes
    assert security_schemes["HolixApiKey"]["type"] == "http"
    assert security_schemes["HolixApiKey"]["scheme"] == "bearer"

    models_op = schema["paths"]["/v1/models"]["get"]
    assert models_op["security"] == [{"HolixApiKey": []}]
    assert "authorization" not in models_op.get("parameters", [])
    assert "x-api-key" not in {p["name"] for p in models_op.get("parameters", [])}