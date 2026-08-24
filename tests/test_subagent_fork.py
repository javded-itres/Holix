"""Fork-in-process: seed child with completed parent turns."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.subagents.base import (
    MemoryAccess,
    ProcessMode,
    SubAgentConfig,
    SubAgentHandle,
    SubAgentStatus,
)
from core.subagents.fork import (
    completed_turn_prefix,
    insert_seed_messages,
    snapshot_messages_for_fork,
)
from core.tools.subagents import DelegateToSubAgentTool


def test_completed_turn_prefix_drops_open_user_turn() -> None:
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "do the work"},
    ]
    prefix = completed_turn_prefix(msgs)
    assert [m["content"] for m in prefix] == ["hello", "hi"]


def test_completed_turn_prefix_drops_open_tool_call() -> None:
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "now"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
        {"role": "tool", "content": "running"},
    ]
    prefix = completed_turn_prefix(msgs)
    assert [m["content"] for m in prefix] == ["hello", "hi"]


def test_first_turn_fork_is_empty() -> None:
    assert snapshot_messages_for_fork([{"role": "user", "content": "only"}]) == []


def test_snapshot_strips_system_and_caps_content() -> None:
    msgs = [
        {"role": "system", "content": "secret"},
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "open"},
    ]
    out = snapshot_messages_for_fork(msgs)
    assert out == [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
    ]


def test_insert_seed_after_system() -> None:
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "task"},
    ]
    seed = [{"role": "user", "content": "prior"}, {"role": "assistant", "content": "ok"}]
    out = insert_seed_messages(messages, seed)
    assert [m["role"] for m in out] == ["system", "user", "assistant", "user"]
    assert out[-1]["content"] == "task"


@pytest.mark.asyncio
async def test_delegate_tool_passes_fork() -> None:
    parent = MagicMock()
    parent.config.enable_subagents = True
    parent.config.profile_name = "default"
    parent.subagents.find_running_duplicate.return_value = None
    handle = SubAgentHandle(
        name="coder",
        config=SubAgentConfig(
            name="coder",
            process_mode=ProcessMode.ASYNC,
            fork=True,
            seed_messages=[{"role": "user", "content": "a"}],
        ),
        status=SubAgentStatus.RUNNING,
        agent_type="coder",
        task_preview="impl",
    )
    parent.subagents.spawn_typed = AsyncMock(return_value=(handle, None))

    raw = await DelegateToSubAgentTool(parent).execute(
        agent_type="coder",
        task="impl",
        fork=True,
    )
    parent.subagents.spawn_typed.assert_awaited()
    kwargs = parent.subagents.spawn_typed.await_args.kwargs
    assert kwargs.get("fork") is True
    data = json.loads(raw)
    assert data["fork"] is True
    assert data["seed_turns"] == 1


def test_fork_config_defaults_isolated_memory_flag() -> None:
    cfg = SubAgentConfig(name="x", fork=True, memory_access=MemoryAccess.ISOLATED)
    assert cfg.fork is True
    assert cfg.memory_access == MemoryAccess.ISOLATED


def test_fork_prompt_mentions_snapshot() -> None:
    from core.subagents.prompt import build_subagent_system_prompt

    cfg = SubAgentConfig(name="coder", system_prompt="You code.", fork=True)
    text = build_subagent_system_prompt(cfg, "fix tests")
    assert "Forked parent context" in text
    assert "snapshot" in text.lower()
