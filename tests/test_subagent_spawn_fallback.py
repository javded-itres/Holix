"""Sub-agent OS-process spawn failures fall back to async mode."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from core.subagents.base import ProcessMode, SubAgentConfig
from core.subagents.communication import ProcessCommunicationBus
from core.subagents.manager import SubAgentManager
from core.subagents.process import SubAgentProcessSpawnError


@pytest.mark.asyncio
async def test_process_spawn_fds_error_falls_back_to_async() -> None:
    parent = MagicMock()
    parent.config = MagicMock(subagent_max_concurrent=4)
    manager = SubAgentManager(parent)

    async_handle = MagicMock()
    process_manager = manager._process_manager
    manager._async_runner.run = AsyncMock(return_value=async_handle)
    manager._comm_bus.register_async = AsyncMock()
    process_manager.run = AsyncMock(
        side_effect=SubAgentProcessSpawnError("bad value(s) in fds_to_keep")
    )

    config = SubAgentConfig(name="coder", process_mode=ProcessMode.PROCESS)
    handle = await manager.spawn_sub_agent(config, "build frontend")

    process_manager.run.assert_awaited_once()
    manager._async_runner.run.assert_awaited_once()
    manager._comm_bus.register_async.assert_awaited_once_with("coder")
    assert handle is async_handle
    assert config.process_mode == ProcessMode.ASYNC
    assert manager._process_spawn_unreliable is True
    assert handle.spawn_fallback_reason == "bad value(s) in fds_to_keep"


def test_resolve_process_mode_defaults_to_async() -> None:
    from types import SimpleNamespace

    from core.subagents.spawn import resolve_process_mode

    cfg = SimpleNamespace(subagent_default_process_mode="async")
    assert resolve_process_mode(cfg) == ProcessMode.ASYNC


def test_process_bus_reset_recreates_queues() -> None:
    bus = ProcessCommunicationBus()
    bus.register("coder")
    first_in = bus.get_input_queue("coder")
    bus.reset()
    bus.register("coder")
    second_in = bus.get_input_queue("coder")
    assert first_in is not second_in


def test_process_bus_register_replaces_stale_queues() -> None:
    bus = ProcessCommunicationBus()
    bus.register("coder")
    first_in = bus.get_input_queue("coder")
    first_out = bus.get_output_queue("coder")
    bus.register("coder")
    second_in = bus.get_input_queue("coder")
    second_out = bus.get_output_queue("coder")
    assert first_in is not second_in
    assert first_out is not second_out