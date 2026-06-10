"""Shared pytest fixtures and markers."""

from __future__ import annotations

import asyncio
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
    from core.di.runtime_config import HelixRuntimeConfig
    from core.memory.facade import MemoryFacade

    cfg = HelixRuntimeConfig.from_settings().with_overrides(
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