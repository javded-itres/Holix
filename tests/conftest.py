"""Shared pytest fixtures and markers."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
import uuid

import pytest
from core.tools.registry import ToolRegistry


def _unique_chroma_collection(request: pytest.FixtureRequest) -> str:
    safe = re.sub(r"[^\w]", "_", request.node.name)[:48]
    return f"test_{safe}_{uuid.uuid4().hex[:8]}"


def pytest_collection_modifyitems(config, items):
    """Auto-apply unit/integration/llm markers from path and names."""
    for item in items:
        if item.get_closest_marker("llm"):
            continue
        if item.get_closest_marker("integration"):
            continue
        if item.get_closest_marker("unit"):
            continue

        nodeid = item.nodeid
        if "test_graph_e2e" in nodeid or "TestRunAgentLoopWithMocks" in nodeid:
            item.add_marker(pytest.mark.integration)
        elif "llm" in item.name.lower():
            item.add_marker(pytest.mark.llm)
        else:
            item.add_marker(pytest.mark.unit)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def temp_dir():
    """Create temporary directory for tests."""
    temp = tempfile.mkdtemp()
    yield temp
    shutil.rmtree(temp, ignore_errors=True)


@pytest.fixture
async def memory_manager(temp_dir, request):
    """Memory facade with isolated SQLite + Chroma collection per test."""
    from core.di.runtime_config import HolixRuntimeConfig
    from core.memory.facade import MemoryFacade

    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        memory_db_path=f"{temp_dir}/test_memory.db",
        vector_db_path=f"{temp_dir}/test_vector_db",
        ltm_db_path=f"{temp_dir}/test_ltm.db",
        memory_chroma_collection=_unique_chroma_collection(request),
        enable_long_term_memory=True,
    )
    manager = MemoryFacade(cfg)
    await manager.initialize_db()

    yield manager


@pytest.fixture
def tools_registry():
    """Create tools registry."""
    registry = ToolRegistry()
    registry.register_all()
    return registry


@pytest.fixture
def skills_manager(temp_dir):
    """Create skills manager with temp directory."""
    from core.skills.manager import SkillsManager

    from config import settings

    original_skills_dir = settings.skills_dir
    settings.skills_dir = f"{temp_dir}/skills"

    manager = SkillsManager()
    yield manager

    settings.skills_dir = original_skills_dir


@pytest.fixture
def gateway_auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-key"}


@pytest.fixture
def gateway_client(gateway_auth_headers, monkeypatch: pytest.MonkeyPatch):
    """TestClient with auth bypass and mocked host-profile agent."""
    from unittest.mock import AsyncMock, MagicMock

    import api.deps
    import api.gateway
    import api.state
    from core.gateway.responses_store import ResponsesStore
    from core.gateway.runs_store import RunsStore
    from core.gateway.sessions_store import SessionsStore
    from fastapi.testclient import TestClient

    mock_agent = AsyncMock()
    mock_agent._initialized = True
    mock_agent.run = AsyncMock(return_value="ok")
    mock_agent.get_tools = MagicMock(return_value=["read_file"])
    mock_agent.get_skills = MagicMock(return_value={})
    mock_agent.get_conversation_history = AsyncMock(return_value=[])
    mock_agent.search_memory = AsyncMock(return_value=[])

    mock_registry = MagicMock()
    mock_registry.get_agent = AsyncMock(return_value=mock_agent)
    mock_registry.entry = MagicMock(return_value=MagicMock(agent=mock_agent))
    mock_registry.list_loaded_profiles = MagicMock(return_value=["default"])

    async def _fake_key():
        return {"permissions": ["read", "write", "execute", "admin"], "rate_limit": 1000}

    async def _fake_registry():
        return mock_registry

    monkeypatch.setattr(api.state, "registry", mock_registry)
    monkeypatch.setattr(api.state, "host_profile", "default")
    monkeypatch.setattr(api.state, "responses_store", ResponsesStore())
    monkeypatch.setattr(api.state, "runs_store", RunsStore())
    monkeypatch.setattr(api.state, "sessions_store", SessionsStore())
    monkeypatch.setattr(api.state, "_agent_request_lock", asyncio.Lock())

    api.gateway.app.dependency_overrides[api.deps.verify_api_key] = _fake_key
    api.gateway.app.dependency_overrides[api.deps.verify_admin_key] = _fake_key
    api.gateway.app.dependency_overrides[api.deps.get_registry] = _fake_registry

    client = TestClient(api.gateway.app)
    yield client
    api.gateway.app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _encryption_mode_for_crypto_tests(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    """Default tests to HOLIX_ENCRYPTION_MODE=on; policy tests control their own mode."""
    if request.node.path.name == "test_encryption_policy.py":
        return
    if "HOLIX_ENCRYPTION_MODE" not in os.environ:
        monkeypatch.setenv("HOLIX_ENCRYPTION_MODE", "on")