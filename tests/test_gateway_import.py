"""Ensure api.gateway module loads and critical endpoints behave."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


def test_gateway_module_imports() -> None:
    import api.gateway  # noqa: F401

    assert api.gateway.app is not None


def test_permissions_endpoints_use_shared_manager() -> None:
    import api.gateway
    from core.security.confirmation import permission_manager

    permission_manager.clear_session()
    client = TestClient(api.gateway.app)
    tool_name = "test_gateway_permission_tool"

    response = client.get("/v1/permissions")
    assert response.status_code == 200
    assert response.json()["session"] == []

    response = client.post(
        "/v1/permissions/grant",
        params={
            "tool_name": tool_name,
            "risk_level": "high",
            "scope": "session",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "granted"

    grants = permission_manager.list_grants()
    session_tools = [g["tool"] for g in grants["session"]]
    assert tool_name in session_tools

    response = client.delete(
        f"/v1/permissions/{tool_name}:high",
        params={"scope": "session"},
    )
    assert response.status_code == 200
    session_tools = [g["tool"] for g in permission_manager.list_grants()["session"]]
    assert tool_name not in session_tools


def test_prometheus_metrics_uses_global_collector() -> None:
    import api.gateway

    client = TestClient(api.gateway.app)
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "helix_" in response.text


def test_per_key_rate_limit_applied(monkeypatch) -> None:
    from api import deps

    class FakeManager:
        def hash_key(self, key: str) -> str:
            return "hash"

        async def validate_api_key(self, key: str):
            return {"permissions": "read,execute", "rate_limit": 2}

    class FakeLimiter:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def check_rate_limit(self, key_hash: str, limit: int, window: int = 60) -> bool:
            self.calls.append((key_hash, limit))
            return True

    limiter = FakeLimiter()
    monkeypatch.setattr(deps, "api_key_manager", FakeManager())
    monkeypatch.setattr(deps, "rate_limiter", limiter)
    monkeypatch.setattr("api.deps.settings.rate_limit_rpm", 100)

    import asyncio

    asyncio.run(deps._validate_key("k", default_limit=100))
    assert limiter.calls == [("hash", 2)]


@pytest.mark.asyncio
async def test_chat_completions_serializes_agent_access() -> None:
    import api.gateway
    from api.models import ChatCompletionRequest, Message

    mock_agent = AsyncMock()
    mock_agent._initialized = True
    mock_agent.run = AsyncMock(return_value="ok")

    request = ChatCompletionRequest(
        model="test",
        messages=[Message(role="user", content="hi")],
        conversation_id="c1",
    )

    with patch.object(api.gateway, "agent", mock_agent):
        response = await api.gateway.chat_completions(request, key_info=None)

    assert response.choices[0]["message"]["content"] == "ok"
    mock_agent.run.assert_awaited_once()