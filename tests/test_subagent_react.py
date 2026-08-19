"""Sub-agents on the main LangGraph ReAct engine."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.graph.nodes.react_node import (
    _apply_supervisor_guidance,
    _build_system_prompt_from_state,
    _maybe_subagent_empty_retry,
)
from core.llm.completion import EMPTY_FINAL_CONTINUE
from core.subagents.base import SubAgentConfig, SubAgentHandle, SubAgentResult
from core.subagents.communication import AgentMessage, AsyncCommunicationBus
from core.subagents.react_agent import (
    FilteredToolRegistry,
    allowed_tool_names,
    attach_subagent_runtime,
    is_empty_react_result,
    is_failed_react_result,
    resolve_subagent_context_window,
)
from core.subagents.supervisor import (
    drain_guidance_from_input_queue,
    format_guidance_system_message,
)


def test_filtered_registry_hides_disallowed_tools() -> None:
    inner = MagicMock()
    inner.get_schemas.return_value = [
        {"function": {"name": "read_file"}},
        {"function": {"name": "write_file"}},
        {"function": {"name": "delegate_to_subagent"}},
        {"function": {"name": "mcp_context7_query-docs"}},
    ]
    inner.tools = {
        "read_file": object(),
        "write_file": object(),
        "delegate_to_subagent": object(),
        "mcp_context7_query-docs": object(),
    }
    reg = FilteredToolRegistry(
        inner,
        allowed={"read_file", "write_file"},
        inherit_mcp=True,
        mcp_servers=[],
    )
    names = [s["function"]["name"] for s in reg.get_schemas()]
    assert "read_file" in names
    assert "write_file" in names
    assert "mcp_context7_query-docs" in names
    assert "delegate_to_subagent" not in names


@pytest.mark.asyncio
async def test_filtered_registry_blocks_execute() -> None:
    inner = MagicMock()
    inner.execute = AsyncMock(return_value="ok")
    reg = FilteredToolRegistry(
        inner,
        allowed={"read_file"},
        inherit_mcp=False,
        mcp_servers=[],
    )
    call = SimpleNamespace(function=SimpleNamespace(name="write_file"))
    out = await reg.execute(call)
    assert "not available" in out
    inner.execute.assert_not_called()


def test_react_prompt_uses_subagent_system_not_main_identity() -> None:
    agent = SimpleNamespace(
        tools=SimpleNamespace(get_schemas=lambda for_agent_slot="main": []),
        skills=None,
        subagent_system_prompt=(
            "You are python-coder, a specialized assistant.\n## Your Task\nfix providers.py"
        ),
        studio_agent_type=None,
        studio_persona_prompt=None,
        config=SimpleNamespace(workspace_root=None, workspace_jail_enabled=None),
    )
    text = _build_system_prompt_from_state(
        {
            "relevant_skills": [],
            "relevant_memories": [],
            "relevant_strategies": [],
            "plan_steps": [],
            "current_plan_step": 0,
            "meta_decision": None,
            "reflection_log": [],
        },
        agent=agent,
    )
    assert "fix providers.py" in text
    assert "specialized assistant" in text


def test_resolve_context_uses_model_not_28k_cap() -> None:
    parent = SimpleNamespace(
        model="qwen3.6_gpu:35b",
        config=SimpleNamespace(context_window=131072),
        active_model_config=None,
        model_manager=None,
    )
    cfg = SubAgentConfig(name="coder", model="qwen3.6_gpu:35b")
    assert resolve_subagent_context_window(parent, cfg) == 131072


def test_resolve_context_prefers_active_model_window() -> None:
    parent = SimpleNamespace(
        model="qwen3.6_gpu:35b",
        config=SimpleNamespace(context_window=131072),
        active_model_config=SimpleNamespace(model="qwen3.6_gpu:35b", context_window=32768),
        model_manager=None,
    )
    assert resolve_subagent_context_window(parent, SubAgentConfig(name="coder")) == 32768


def test_resolve_context_from_provider_model_contexts() -> None:
    mm = SimpleNamespace(
        profile_config=SimpleNamespace(
            agent_models={},
            providers={
                "litellm": {"model_contexts": {"qwen3.6_gpu:35b": 65536}},
            },
        )
    )
    parent = SimpleNamespace(
        model="other",
        config=SimpleNamespace(context_window=131072),
        active_model_config=None,
        model_manager=mm,
    )
    cfg = SubAgentConfig(name="coder", model="qwen3.6_gpu:35b")
    assert resolve_subagent_context_window(parent, cfg) == 65536


def test_allowed_tool_names() -> None:
    cfg = SubAgentConfig(name="coder", tools=["read_file", "write_file", ""])
    assert allowed_tool_names(cfg) == {"read_file", "write_file"}


def test_filtered_registry_forwards_unknown_attrs() -> None:
    inner = SimpleNamespace(_mcp_manager="mgr", extra=7)
    reg = FilteredToolRegistry(inner, allowed={"read_file"}, inherit_mcp=False, mcp_servers=[])
    assert reg._mcp_manager == "mgr"
    assert reg.extra == 7


def test_empty_react_result_detects_placeholders() -> None:
    assert is_empty_react_result("")
    assert is_empty_react_result("No response")
    assert is_empty_react_result("Agent completed without producing a final response.")
    assert is_empty_react_result("Finished reasoning without a visible answer.")
    assert not is_empty_react_result("patched providers.py")


def test_failed_react_result_treats_timeout_as_failure() -> None:
    err = is_failed_react_result("Error during agent step: Request timed out.")
    assert err
    assert "timed out" in err.lower() or "error" in err.lower()
    assert is_failed_react_result("") == "empty LLM reply (no text, no tools)"
    assert is_failed_react_result("patched providers.py and tests pass") is None


def test_subagent_empty_reply_keeps_react_open() -> None:
    agent = SimpleNamespace(subagent_system_prompt="You are coder", emit=lambda *_a, **_k: None)
    out = _maybe_subagent_empty_retry(
        agent=agent,
        conversation_id="subagent:coder",
        messages=[{"role": "user", "content": "fix it"}],
        step_count=2,
        final_response="No response",
    )
    assert out is not None
    assert out["is_final"] is False
    assert out["final_response"] == ""
    assert any(m.get("content") == EMPTY_FINAL_CONTINUE for m in out["messages"])


def test_main_agent_empty_reply_is_not_subagent_retry() -> None:
    agent = SimpleNamespace(subagent_system_prompt="", emit=lambda *_a, **_k: None)
    assert (
        _maybe_subagent_empty_retry(
            agent=agent,
            conversation_id="default",
            messages=[],
            step_count=1,
            final_response="",
        )
        is None
    )


def test_subagent_empty_reply_fails_after_three_continues() -> None:
    agent = SimpleNamespace(subagent_system_prompt="You are coder", emit=lambda *_a, **_k: None)
    messages = [
        {"role": "system", "content": EMPTY_FINAL_CONTINUE},
        {"role": "system", "content": EMPTY_FINAL_CONTINUE},
        {"role": "system", "content": EMPTY_FINAL_CONTINUE},
    ]
    out = _maybe_subagent_empty_retry(
        agent=agent,
        conversation_id="subagent:coder",
        messages=messages,
        step_count=6,
        final_response="",
    )
    assert out is not None
    assert out["is_final"] is True
    assert out["final_response"] == ""


def test_empty_react_wrapper_result_shape() -> None:
    result = SubAgentResult(
        name="coder",
        success=False,
        error="empty LLM reply (no text, no tools)",
        response="No response",
    )
    handle = SubAgentHandle(name="coder", config=SubAgentConfig(name="coder"))
    handle.result = result
    assert result.success is False
    assert "empty" in (result.error or "")


class _Queue:
    def __init__(self, items: list) -> None:
        self._items = list(items)

    def get_nowait(self):
        if not self._items:
            raise Exception("empty")
        return self._items.pop(0)


def test_drain_process_queue_guidance_and_cancel() -> None:
    q = _Queue(
        [
            AgentMessage(
                from_agent="supervisor",
                to_agent="coder",
                msg_type="guidance",
                content="Stop looping on read_file",
            ).serialize(),
            AgentMessage(
                from_agent="main",
                to_agent="coder",
                msg_type="cancel",
            ).serialize(),
        ]
    )
    texts, cancelled = drain_guidance_from_input_queue(q)
    assert texts == ["Stop looping on read_file"]
    assert cancelled is True


@pytest.mark.asyncio
async def test_react_node_applies_async_supervisor_guidance() -> None:
    bus = AsyncCommunicationBus()
    await bus.register("coder-1")
    await bus.send(
        AgentMessage(
            from_agent="supervisor",
            to_agent="coder-1",
            msg_type="guidance",
            content="Do not retry the same pytest command",
        )
    )
    seen: list[str] = []
    agent = SimpleNamespace(subagent_system_prompt="You are coder")
    attach_subagent_runtime(
        agent,
        name="coder-1",
        receive=bus.receive,
        on_guidance=lambda: seen.append("applied"),
    )
    messages, patch, cancelled = await _apply_supervisor_guidance(
        agent,
        [{"role": "user", "content": "fix tests"}],
        conversation_id="subagent:coder-1",
    )
    assert cancelled is False
    assert seen == ["applied"]
    assert any("Runtime supervisor intervention" in (m.get("content") or "") for m in messages)
    assert "Do not retry the same pytest command" in (patch["messages"][-1]["content"])


@pytest.mark.asyncio
async def test_react_node_cancel_from_process_queue() -> None:
    q = _Queue(
        [
            AgentMessage(
                from_agent="main",
                to_agent="coder",
                msg_type="cancel",
            ).serialize(),
        ]
    )
    agent = SimpleNamespace(subagent_system_prompt="You are coder")
    attach_subagent_runtime(agent, name="coder", input_queue=q)
    _messages, _patch, cancelled = await _apply_supervisor_guidance(
        agent,
        [{"role": "user", "content": "fix it"}],
        conversation_id="subagent:coder",
    )
    assert cancelled is True


@pytest.mark.asyncio
async def test_main_agent_does_not_drain_guidance() -> None:
    agent = SimpleNamespace(subagent_system_prompt="")
    messages, patch, cancelled = await _apply_supervisor_guidance(
        agent,
        [{"role": "user", "content": "hi"}],
        conversation_id="default",
    )
    assert messages[0]["content"] == "hi"
    assert patch == {}
    assert cancelled is False


def test_format_guidance_still_prefixed() -> None:
    text = format_guidance_system_message(["switch strategy"])
    assert "Runtime supervisor intervention" in text
    assert "switch strategy" in text
