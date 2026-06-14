"""Sub-agent duplicate spawn prevention."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.subagents.base import ProcessMode, SubAgentConfig, SubAgentHandle, SubAgentStatus
from core.tools.subagents import DelegateToSubAgentTool


def _running_handle(name: str, *, agent_type: str, task: str) -> SubAgentHandle:
    return SubAgentHandle(
        name=name,
        config=SubAgentConfig(name=name, process_mode=ProcessMode.ASYNC),
        status=SubAgentStatus.RUNNING,
        agent_type=agent_type,
        task_preview=task,
    )


@pytest.mark.asyncio
async def test_delegate_tool_reuses_running_duplicate() -> None:
    parent = MagicMock()
    parent.config.enable_subagents = True
    existing = _running_handle("researcher", agent_type="researcher", task="Find SaaS competitors")
    parent.subagents.find_running_duplicate.return_value = existing
    parent.subagents.spawn_typed = AsyncMock()

    tool = DelegateToSubAgentTool(parent)
    raw = await tool.execute(agent_type="researcher", task="Find SaaS competitors")
    data = json.loads(raw)

    assert data["status"] == "already_running"
    assert data["job_id"] == "researcher"
    parent.subagents.spawn_typed.assert_not_called()


def test_find_running_duplicate_matches_task_preview() -> None:
    from core.subagents.manager import SubAgentManager

    parent = MagicMock()
    mgr = SubAgentManager(parent)
    handle = _running_handle("coder", agent_type="coder", task="Implement REST endpoint")
    mgr._handles["coder"] = handle

    found = mgr.find_running_duplicate("coder", "Implement REST endpoint")
    assert found is handle