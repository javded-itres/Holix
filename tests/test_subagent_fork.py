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
    bind_subagent_session,
    child_conversation_id,
    completed_turn_prefix,
    insert_seed_messages,
    parent_conversation_id,
    parent_from_child_conversation_id,
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


def test_parent_conversation_id_skips_default_and_child_cid(monkeypatch) -> None:
    from core.agent_events import EventContext
    from core.tools.execution_context import conversation_scope, reset_conversation_scope

    parent = MagicMock()
    parent.conversation_id = "agent-attr"
    parent._event_context = EventContext(conversation_id="studio_tab_a")

    tok = conversation_scope("default")
    try:
        assert parent_conversation_id(parent) == "studio_tab_a"
    finally:
        reset_conversation_scope(tok)

    tok = conversation_scope("subagent:studio_tab_a:coder")
    try:
        assert parent_conversation_id(parent) == "studio_tab_a"
    finally:
        reset_conversation_scope(tok)

    tok = conversation_scope("studio_tab_b")
    try:
        assert parent_conversation_id(parent) == "studio_tab_b"
    finally:
        reset_conversation_scope(tok)


def test_child_conversation_id_is_namespaced_and_fits_safe_cid() -> None:
    from core.sdd.change_workspace import _safe_cid

    parent = "studio_pavel_it-rs.ru_main_1789692156998648475_502258"
    child = child_conversation_id(parent, "coder-python-1")
    assert child == f"subagent:{parent}:coder-python-1"
    assert _safe_cid(child) == child
    assert parent_from_child_conversation_id(child) == parent
    assert parent_from_child_conversation_id("subagent:coder") == ""
    other = child_conversation_id("studio_other_tab", "coder-python-1")
    assert other != child


def test_bind_subagent_session_inherits_parent_pin_not_global_alias(
    tmp_path,
) -> None:
    from core.sdd.change_workspace import (
        bind_active_project,
        get_active_change,
        overlay_workspace_root,
        reset_active_change_store,
    )
    from core.tools.execution_context import conversation_scope, reset_conversation_scope

    reset_active_change_store()
    proj_a = tmp_path / "proj_a"
    proj_b = tmp_path / "proj_b"
    proj_a.mkdir()
    proj_b.mkdir()
    bind_active_project("default", "sess_a", proj_a, project="proj_a")
    bind_active_project("default", "sess_b", proj_b, project="proj_b")

    parent_a = MagicMock()
    parent_a.config.profile_name = "default"
    parent_a.config.workspace_root = str(tmp_path)
    parent_a._event_context = None
    parent_a.conversation_id = "sess_a"

    cfg = SubAgentConfig(name="coder-python")
    handle = SubAgentHandle(name="coder-python", config=cfg)
    tok = conversation_scope("sess_a")
    try:
        parent_cid, child_cid = bind_subagent_session(parent_a, cfg, handle)
    finally:
        reset_conversation_scope(tok)
    assert parent_cid == "sess_a"
    assert child_cid == "subagent:sess_a:coder-python"
    assert handle.parent_conversation_id == "sess_a"
    assert handle.conversation_id == child_cid
    assert overlay_workspace_root("default", child_cid) == str(proj_a.resolve())
    assert get_active_change("default", "subagent:coder-python") is None

    parent_b = MagicMock()
    parent_b.config.profile_name = "default"
    parent_b.config.workspace_root = str(tmp_path)
    parent_b._event_context = None
    parent_b.conversation_id = "sess_b"
    cfg_b = SubAgentConfig(name="coder-python")
    handle_b = SubAgentHandle(name="coder-python", config=cfg_b)
    tok = conversation_scope("sess_b")
    try:
        _parent_b, child_b = bind_subagent_session(parent_b, cfg_b, handle_b)
    finally:
        reset_conversation_scope(tok)
    assert child_b != child_cid
    assert overlay_workspace_root("default", child_cid) == str(proj_a.resolve())
    assert overlay_workspace_root("default", child_b) == str(proj_b.resolve())
    reset_active_change_store()
