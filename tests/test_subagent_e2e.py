"""End-to-end sub-agent spawn → wait → result (async mode, mocked LLM)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.subagents.base import ProcessMode, SubAgentConfig, SubAgentStatus
from core.subagents.manager import SubAgentManager
from core.subagents.spawn import prepare_subagent_config
from core.tools.registry import ToolRegistry
from core.tools.subagents import (
    DelegateToSubAgentTool,
    ListSubAgentsTool,
    WaitSubAgentResultTool,
)


def _llm_final_response(text: str) -> MagicMock:
    message = MagicMock()
    message.content = text
    message.tool_calls = None
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _parent_with_mock_llm(*, response_text: str = "SUBAGENT_OK") -> MagicMock:
    parent = MagicMock()
    parent.model = "test-model"
    parent.config = SimpleNamespace(
        enable_subagents=True,
        subagent_max_concurrent=4,
        subagent_default_process_mode="async",
        subagent_process_timeout=30.0,
        profile_name="default",
        confirmation_timeout=0,
        mcp_assignments={},
    )
    parent.skills = None
    parent.memory = None
    parent.tools = ToolRegistry(profile_name="default")
    parent.tools.register_all()

    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_llm_final_response(response_text)
    )
    parent.client = client
    parent.subagents = SubAgentManager(parent)
    return parent


@pytest.mark.asyncio
async def test_async_subagent_spawn_wait_returns_result() -> None:
    parent = _parent_with_mock_llm(response_text="frontend scaffold done")
    mgr = parent.subagents
    cfg = prepare_subagent_config("coder", parent.config, instance_name="coder")

    assert cfg.process_mode == ProcessMode.ASYNC

    handle = await mgr.spawn_sub_agent(cfg, "build frontend", agent_type="coder")
    assert handle.status == SubAgentStatus.RUNNING

    summary = mgr.get_status_summary()
    assert summary["total"] == 1
    assert summary["running"] == 1

    result = await mgr.wait_for(handle.name, timeout=5.0)
    assert result.success is True
    assert result.response == "frontend scaffold done"

    summary_after = mgr.get_status_summary()
    assert summary_after["completed"] == 1
    assert summary_after["running"] == 0


@pytest.mark.asyncio
async def test_delegate_list_wait_tools_roundtrip() -> None:
    parent = _parent_with_mock_llm(response_text="task complete")
    delegate = DelegateToSubAgentTool(parent)
    list_tool = ListSubAgentsTool(parent)
    wait_tool = WaitSubAgentResultTool(parent)

    before = json.loads(await list_tool.execute())
    assert before["total"] == 0

    spawned_raw = await delegate.execute(
        agent_type="writer",
        task="write a one-line summary",
    )
    spawned = json.loads(spawned_raw)
    assert spawned["status"] == "spawned"
    assert spawned["job_id"]
    assert spawned["process_mode"] == "async"

    during = json.loads(await list_tool.execute())
    assert during["total"] >= 1
    assert during["running"] >= 1 or during["completed"] >= 1

    waited_raw = await wait_tool.execute(job_id=spawned["job_id"], timeout_seconds=5.0)
    waited = json.loads(waited_raw)
    assert waited["success"] is True
    assert waited["response"] == "task complete"

    after = json.loads(await list_tool.execute())
    assert after["completed"] >= 1


@pytest.mark.asyncio
async def test_process_spawn_fallback_still_returns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.subagents.process import SubAgentProcessSpawnError

    parent = _parent_with_mock_llm(response_text="fallback ok")
    mgr = parent.subagents
    cfg = SubAgentConfig(name="coder", agent_type="coder", process_mode=ProcessMode.PROCESS)

    mgr._process_manager.run = AsyncMock(
        side_effect=SubAgentProcessSpawnError("bad value(s) in fds_to_keep")
    )

    from unittest.mock import patch

    with patch("core.subagents.manager.process_subagents_supported", return_value=True):
        handle = await mgr.spawn_sub_agent(cfg, "build api", agent_type="coder")
    assert handle.config.process_mode == ProcessMode.ASYNC
    assert handle.spawn_fallback_reason == "bad value(s) in fds_to_keep"

    result = await mgr.wait_for(handle.name, timeout=5.0)
    assert result.success is True
    assert result.response == "fallback ok"