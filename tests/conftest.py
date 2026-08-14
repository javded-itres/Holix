"""Shared pytest fixtures and markers."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

try:
    from integrations.bootstrap import register_integration_hooks

    register_integration_hooks()
except Exception:
    pass
from core.tools.registry import ToolRegistry


def _unique_chroma_collection(request: pytest.FixtureRequest) -> str:
    safe = re.sub(r"[^\w]", "_", request.node.name)[:48]
    return f"test_{safe}_{uuid.uuid4().hex[:8]}"


def pytest_collection_modifyitems(config, items):
    """Auto-apply unit/integration/llm/user_case markers from path and names."""
    for item in items:
        if item.get_closest_marker("llm"):
            continue

        nodeid = item.nodeid
        in_live_llm = "live_llm/" in nodeid or "live_llm\\" in nodeid
        if in_live_llm or item.get_closest_marker("live_llm"):
            if not item.get_closest_marker("live_llm"):
                item.add_marker(pytest.mark.live_llm)
            if not item.get_closest_marker("llm"):
                item.add_marker(pytest.mark.llm)
            continue

        in_tui = (
            "tests/tui/" in nodeid
            or "tests\\tui\\" in nodeid
            or "/tui/" in nodeid
            or "\\tui\\" in nodeid
        )
        if in_tui or item.get_closest_marker("tui"):
            if not item.get_closest_marker("tui"):
                item.add_marker(pytest.mark.tui)
            if not item.get_closest_marker("integration"):
                item.add_marker(pytest.mark.integration)
            continue

        in_user_cases = "user_cases/" in nodeid or "user_cases\\" in nodeid
        if in_user_cases or item.get_closest_marker("user_case"):
            if not item.get_closest_marker("user_case"):
                item.add_marker(pytest.mark.user_case)
            if not item.get_closest_marker("integration"):
                item.add_marker(pytest.mark.integration)
            continue

        if item.get_closest_marker("integration"):
            continue
        if item.get_closest_marker("unit"):
            continue

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
    """TestClient with auth bypass and mocked host-profile agent.

    FromDishka endpoints resolve via ``app.state.dishka_container``; keep that
    container in sync with ``api.state`` mocks used by tests.
    """
    from unittest.mock import AsyncMock, MagicMock

    import api.deps
    import api.gateway
    import api.state
    from core.gateway.companions import CompanionManager
    from core.gateway.locks import GatewayLocks
    from core.gateway.profile_registry import ProfileAgentRegistry
    from core.gateway.responses_store import ResponsesStore
    from core.gateway.runs_store import RunsStore
    from core.gateway.sessions_store import SessionsStore
    from core.gateway.types import HostProfileName
    from core.security.auth import APIKeyManager, RateLimiter
    from fastapi.testclient import TestClient

    mock_agent = AsyncMock()
    mock_agent._initialized = True
    mock_agent.run = AsyncMock(return_value="ok")
    mock_agent.get_tools = MagicMock(return_value=["read_file"])
    mock_agent.get_skills = MagicMock(return_value={})
    mock_agent.get_conversation_history = AsyncMock(return_value=[])
    mock_agent.search_memory = AsyncMock(return_value=[])

    mock_registry = MagicMock()
    mock_registry.host_profile = "default"
    mock_registry.get_agent = AsyncMock(return_value=mock_agent)
    mock_registry.entry = MagicMock(return_value=MagicMock(agent=mock_agent))
    mock_registry.list_loaded_profiles = MagicMock(return_value=["default"])

    responses_store = ResponsesStore()
    runs_store = RunsStore()
    sessions_store = SessionsStore()
    companions = CompanionManager()
    locks = GatewayLocks()
    rate_limiter = RateLimiter()

    async def _fake_key():
        return {"permissions": ["read", "write", "execute", "admin"], "rate_limit": 1000}

    monkeypatch.setattr(api.state, "registry", mock_registry)
    monkeypatch.setattr(api.state, "host_profile", "default")
    monkeypatch.setattr(api.state, "responses_store", responses_store)
    monkeypatch.setattr(api.state, "runs_store", runs_store)
    monkeypatch.setattr(api.state, "sessions_store", sessions_store)
    monkeypatch.setattr(api.state, "companions", companions)
    monkeypatch.setattr(api.state, "gateway_locks", locks)
    monkeypatch.setattr(api.state, "_agent_request_lock", locks.agent_request)
    monkeypatch.setattr(api.state, "rate_limiter", rate_limiter)

    from contextlib import asynccontextmanager

    class _OverlayContainer:
        """Route FromDishka lookups to test doubles; fall back to real container."""

        def __init__(self, base, overrides: dict):
            self._base = base
            self._overrides = overrides

        async def get(self, dependency_type, component: str | None = ""):
            if dependency_type in self._overrides:
                return self._overrides[dependency_type]
            if dependency_type is APIKeyManager and api.state.api_key_manager is not None:
                return api.state.api_key_manager
            return await self._base.get(dependency_type, component)

        def __call__(self, context=None, scope=None):
            """Dishka middleware opens a REQUEST scope via container(...)."""

            @asynccontextmanager
            async def _cm():
                async with self._base(context=context, scope=scope) as request_container:
                    yield _OverlayContainer(request_container, self._overrides)

            return _cm()

        async def close(self):
            return await self._base.close()

        def __getattr__(self, name: str):
            return getattr(self._base, name)

    base_container = api.gateway.app.state.dishka_container
    overlay = _OverlayContainer(
        base_container,
        {
            ProfileAgentRegistry: mock_registry,
            ResponsesStore: responses_store,
            RunsStore: runs_store,
            SessionsStore: sessions_store,
            CompanionManager: companions,
            GatewayLocks: locks,
            HostProfileName: HostProfileName("default"),
            RateLimiter: rate_limiter,
        },
    )
    # Dishka middleware and routes read container from app.state
    api.gateway.app.state.dishka_container = overlay

    api.gateway.app.dependency_overrides[api.deps.verify_api_key] = _fake_key
    api.gateway.app.dependency_overrides[api.deps.verify_admin_key] = _fake_key
    if hasattr(api.deps, "get_registry"):
        api.gateway.app.dependency_overrides[api.deps.get_registry] = lambda: mock_registry

    client = TestClient(api.gateway.app)
    yield client
    api.gateway.app.state.dishka_container = base_container
    api.gateway.app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_env_loader_state() -> None:
    """Keep env bootstrap shell-lock state from leaking across tests."""
    import core.env_loader as el

    el._BOOTSTRAPPED = False
    el._SHELL_ENV_KEYS = None
    el._ACTIVE_PROFILE_ENV = None
    yield
    el._BOOTSTRAPPED = False
    el._SHELL_ENV_KEYS = None
    el._ACTIVE_PROFILE_ENV = None


@pytest.fixture(autouse=True)
def _isolated_holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep profile paths off the developer/CI machine (~/.holix)."""
    import cli.core as cli_core
    from core.profile import service as profile_service

    holix_home = tmp_path / ".holix"
    profiles = holix_home / "profiles"
    logs = holix_home / "logs"
    profiles.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    # Avoid leaking profile selection from other tests into gateway import-time DI.
    monkeypatch.delenv("HOLIX_PROFILE", raising=False)
    # Implementation lives in core; keep cli.core attrs in sync for patches.
    for mod in (profile_service, cli_core):
        monkeypatch.setattr(mod, "HOLIX_HOME", holix_home, raising=False)
        monkeypatch.setattr(mod, "PROFILES_DIR", profiles, raising=False)
        monkeypatch.setattr(mod, "LOGS_DIR", logs, raising=False)
    # Reset process-level profile session so tests do not leak names/paths.
    profile_service._current_profile = None
    profile_service._current_config = None
    profile_service._unlocked_profiles.clear()
    profile_service._profile_manager = profile_service.ProfileManager()


@pytest.fixture(autouse=True)
def _encryption_mode_for_crypto_tests(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
):
    """Default tests to HOLIX_ENCRYPTION_MODE=on; policy tests control their own mode."""
    if request.node.path.name == "test_encryption_policy.py":
        return
    if "HOLIX_ENCRYPTION_MODE" not in os.environ:
        monkeypatch.setenv("HOLIX_ENCRYPTION_MODE", "on")
