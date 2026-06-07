"""Tests for Dishka DI and HelixRuntimeConfig."""

from pathlib import Path

import pytest

from core.di.runtime_config import HelixRuntimeConfig
from core.di.container import create_async_container, create_agent, resolve_runtime_config
from core.agent import HelixAgent
from cli.core import ProfileConfig


def test_runtime_config_from_settings():
    cfg = HelixRuntimeConfig.from_settings()
    assert cfg.model
    assert cfg.memory_db_path
    assert cfg.use_langgraph is True


def test_runtime_config_with_overrides():
    base = HelixRuntimeConfig.from_settings()
    updated = base.with_overrides(model="test-model", max_steps=99)
    assert updated.model == "test-model"
    assert updated.max_steps == 99
    assert base.model != updated.model


def test_runtime_config_from_profile():
    profile = ProfileConfig(
        profile_name="test",
        model="profile-model",
        memory_db_path="/tmp/test_memory.db",
        vector_db_path="/tmp/test_vector",
        skills_dir="/tmp/test_skills",
    )
    cfg = HelixRuntimeConfig.from_profile(profile)
    assert cfg.model == "profile-model"
    assert Path(cfg.memory_db_path).resolve() == Path("/tmp/test_memory.db").resolve()
    assert cfg.profile_name == "test"


@pytest.mark.asyncio
async def test_create_async_container_without_explicit_config():
    container = create_async_container()
    try:
        from core.agent import HelixAgent

        agent = await container.get(HelixAgent)
        assert agent.config.model
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_dishka_container_provides_agent(temp_dir):
    cfg = HelixRuntimeConfig.from_settings().with_overrides(
        memory_db_path=f"{temp_dir}/mem.db",
        vector_db_path=f"{temp_dir}/vec",
        ltm_db_path=f"{temp_dir}/ltm.db",
        skills_dir=f"{temp_dir}/skills",
    )
    from core.agent import HelixAgent

    container = create_async_container(cfg)
    try:
        agent = await container.get(HelixAgent)
        assert agent.config.memory_db_path == cfg.memory_db_path
        assert agent.model == cfg.model
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_create_agent_initializes(memory_manager, temp_dir):
    """create_agent uses profile paths without mutating global settings."""
    profile = ProfileConfig(
        profile_name="di_test",
        memory_db_path=f"{temp_dir}/mem.db",
        vector_db_path=f"{temp_dir}/vec",
        skills_dir=f"{temp_dir}/skills",
    )
    runtime_config = resolve_runtime_config(profile)
    container = None
    try:
        agent, container = await create_agent(
            runtime_config,
            enable_monitoring=False,
        )
        assert agent._initialized
        assert Path(agent.config.memory_db_path).resolve() == Path(
            f"{temp_dir}/mem.db"
        ).resolve()
    finally:
        if container:
            await container.close()