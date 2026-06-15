"""Sub-agent platform behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.subagents.base import ProcessMode, SubAgentConfig
from core.subagents.manager import SubAgentManager
from core.subagents.process import SubAgentProcessManager, _ensure_event_loop


def test_ensure_event_loop_creates_loop_on_fresh_thread() -> None:
    import asyncio

    asyncio.set_event_loop(asyncio.new_event_loop())
    asyncio.get_event_loop().close()
    asyncio.set_event_loop(None)

    loop = _ensure_event_loop()
    assert loop is not None
    assert not loop.is_closed()
    loop.run_until_complete(asyncio.sleep(0))


@pytest.mark.asyncio
async def test_windows_process_mode_falls_back_to_async() -> None:
    parent = MagicMock()
    parent.model = "test-model"
    manager = SubAgentManager(parent)

    config = SubAgentConfig(
        name="worker",
        process_mode=ProcessMode.PROCESS,
    )
    async_handle = MagicMock()
    manager._async_runner.run = AsyncMock(return_value=async_handle)
    manager._comm_bus.register_async = AsyncMock()

    with patch("core.subagents.manager.process_subagents_supported", return_value=False):
        handle = await manager.spawn_sub_agent(config, task="do work")

    manager._async_runner.run.assert_awaited_once()
    manager._process_manager.run = AsyncMock()
    assert handle is async_handle


@pytest.mark.asyncio
async def test_process_spawn_reads_parent_config_not_runtime_config() -> None:
    parent = MagicMock()
    parent.model = "smart"
    parent.config = MagicMock(
        base_url="http://localhost:4000/v1",
        api_key="sk-test",
        auto_allow_threshold="low",
        confirmation_timeout=300,
        non_interactive=False,
        mcp_servers={},
        skills_dir="/tmp/skills",
        skill_assignments={},
    )
    parent.memory = None

    captured_args: list = []
    env_captured: dict[str, str] = {}

    class FakeProcess:
        pid = 4242

        def __init__(self, target, args, daemon):
            captured_args.extend(args)

        def start(self):
            return None

    def fake_start(process, *, api_key: str, base_url: str, preset_id: str = "") -> None:
        env_captured["api_key"] = api_key
        env_captured["base_url"] = base_url
        env_captured["preset_id"] = preset_id

    mgr = SubAgentProcessManager(parent)
    config = SubAgentConfig(name="researcher", process_mode=ProcessMode.PROCESS)

    fake_ctx = MagicMock()
    fake_ctx.Process = FakeProcess
    with patch("core.subagents.process.subagent_mp_context", return_value=fake_ctx):
        with patch("core.subagents.process._start_subagent_process", side_effect=fake_start):
            with patch("core.subagents.process.asyncio.create_task"):
                await mgr.run(config, "find docs")

    assert captured_args[4] == "smart"
    assert env_captured == {
        "api_key": "sk-test",
        "base_url": "http://localhost:4000/v1",
        "preset_id": "",
    }
    assert "sk-test" not in " ".join(str(a) for a in captured_args)


@pytest.mark.asyncio
async def test_process_spawn_serializes_agent_type() -> None:
    parent = MagicMock()
    parent.model = "coder"
    parent.config = MagicMock(
        base_url="http://localhost:4000/v1",
        api_key="sk-test",
        auto_allow_threshold="low",
        confirmation_timeout=300,
        non_interactive=False,
        mcp_servers={},
        skills_dir="/tmp/skills",
        skill_assignments={},
        search={},
        profile_name="default",
        data_dir="/tmp/data",
        ltm_db_path="",
        vector_db_path="",
    )
    parent.memory = None

    captured_args: list = []

    class FakeProcess:
        pid = 4243

        def __init__(self, target, args, daemon):
            captured_args.extend(args)

        def start(self) -> None:
            return None

    mgr = SubAgentProcessManager(parent)
    config = SubAgentConfig(
        name="coder",
        agent_type="coder",
        process_mode=ProcessMode.PROCESS,
        tools=["external_cli"],
    )

    fake_ctx = MagicMock()
    fake_ctx.Process = FakeProcess
    with patch("core.subagents.process.subagent_mp_context", return_value=fake_ctx):
        with patch("core.subagents.process._start_subagent_process"):
            with patch("core.subagents.process.asyncio.create_task"):
                await mgr.run(config, "launch external cli")

    config_dict = captured_args[0]
    assert config_dict["agent_type"] == "coder"
    rebuilt = SubAgentConfig(**config_dict)
    assert rebuilt.agent_type == "coder"