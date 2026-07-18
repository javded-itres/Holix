"""Architecture / DI integration tests."""

from __future__ import annotations

import pytest
from core.agent import HolixAgent
from core.di.container import create_agent, create_async_container
from core.di.runtime_config import HolixRuntimeConfig
from core.domain.graph_runtime import GraphRuntime
from core.runtime.agent_sessions import get_agent_session, register_agent_session
from core.runtime.background_process import (
    BackgroundProcessRegistry,
    bind_background_process_registry,
    get_background_process_registry,
)


@pytest.mark.asyncio
async def test_dishka_provides_all_agent_services(temp_dir) -> None:
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        memory_db_path=f"{temp_dir}/mem.db",
        vector_db_path=f"{temp_dir}/vec",
        ltm_db_path=f"{temp_dir}/ltm.db",
        skills_dir=f"{temp_dir}/skills",
        profile_name="arch_test",
    )
    container = create_async_container(cfg)
    try:
        from core.context import ContextManager
        from core.memory.facade import MemoryFacade
        from core.search.engine import SearchEngine
        from core.skills.manager import SkillsManager
        from core.tools.registry import ToolRegistry

        memory = await container.get(MemoryFacade)
        tools = await container.get(ToolRegistry)
        skills = await container.get(SkillsManager)
        context = await container.get(ContextManager)
        search = await container.get(SearchEngine)
        bg = await container.get(BackgroundProcessRegistry)

        assert memory is not None
        assert tools is not None
        assert skills is not None
        assert context is not None
        assert search is not None
        assert bg is not None
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_create_agent_registers_session(temp_dir) -> None:
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        memory_db_path=f"{temp_dir}/mem.db",
        vector_db_path=f"{temp_dir}/vec",
        ltm_db_path=f"{temp_dir}/ltm.db",
        skills_dir=f"{temp_dir}/skills",
        profile_name="sess_test",
    )
    agent, container = await create_agent(cfg, enable_monitoring=False)
    try:
        assert agent._initialized
        assert get_agent_session("sess_test") is agent
        assert agent.background_processes is get_background_process_registry("sess_test")
        assert agent.search is not None
        assert agent._action_guard is not None
        assert agent._plan_review_guard is not None
    finally:
        await agent.close()
        await container.close()


def test_graph_runtime_from_agent() -> None:
    cfg = HolixRuntimeConfig.from_settings()
    agent = HolixAgent(config=cfg, enable_monitoring=False)
    runtime = GraphRuntime.from_agent(agent)
    assert runtime.client is agent.client
    assert runtime.memory is agent.memory
    assert runtime.agent is agent


def test_profile_bound_background_registry() -> None:
    reg = BackgroundProcessRegistry()
    bind_background_process_registry(reg, "p1")
    assert get_background_process_registry("p1") is reg