"""Test helpers for constructing agents without production side effects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from core.agent import HolixAgent
from core.di.runtime_config import HolixRuntimeConfig


def make_runtime_config(temp_dir: str | Path, **overrides: Any) -> HolixRuntimeConfig:
    root = Path(temp_dir)
    return HolixRuntimeConfig.from_settings().with_overrides(
        memory_db_path=str(root / "mem.db"),
        vector_db_path=str(root / "vec"),
        ltm_db_path=str(root / "ltm.db"),
        skills_dir=str(root / "skills"),
        profile_name=overrides.pop("profile_name", "test"),
        **overrides,
    )


def make_test_agent(
    temp_dir: str | Path,
    *,
    enable_monitoring: bool = False,
    **config_overrides: Any,
) -> HolixAgent:
    """Build HolixAgent with defaults (unit tests). Prefer create_agent for integration."""
    cfg = make_runtime_config(temp_dir, **config_overrides)
    return HolixAgent(config=cfg, enable_monitoring=enable_monitoring)


@pytest.fixture
async def di_agent(temp_dir, memory_manager=None):
    """Async fixture: agent via Dishka create_agent."""
    from core.di.container import create_agent

    cfg = make_runtime_config(temp_dir)
    agent, container = await create_agent(cfg, enable_monitoring=False)
    try:
        yield agent
    finally:
        await agent.close()
        await container.close()
