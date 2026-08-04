"""Successful react drafts must not emit FinalResponseEvent (defer to graph end)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.agent_events import FinalResponseEvent
from core.graph.nodes.react_node import _emit_final_response


def test_emit_final_response_sets_flag_for_hard_errors() -> None:
    agent = MagicMock()
    agent._final_response_emitted = False
    _emit_final_response(
        agent,
        content="Error: No LLM client available",
        steps_taken=1,
        conversation_id="c1",
    )
    assert agent._final_response_emitted is True
    assert agent.emit.call_count == 1
    event = agent.emit.call_args[0][0]
    assert isinstance(event, FinalResponseEvent)
    assert "No LLM client" in event.content


@pytest.mark.asyncio
async def test_non_streaming_success_does_not_emit_final() -> None:
    """Draft answer sets is_final but must not bus-emit FinalResponseEvent."""
    from core.graph.nodes import react_node as rn

    message = SimpleNamespace(
        content="Что сделаю: изучу код. Начинаю.",
        tool_calls=None,
        reasoning_content=None,
        reasoning=None,
    )
    choice = SimpleNamespace(message=message, finish_reason="stop")
    response = SimpleNamespace(choices=[choice], usage=None)

    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)

    agent = MagicMock()
    agent.client = client
    agent.model = "smart"
    agent.config = SimpleNamespace(temperature=0.7, llm_step_timeout=30)
    agent.tools = MagicMock()
    agent.tools.get_schemas.return_value = []
    agent.memory = AsyncMock()
    agent.emit = MagicMock()
    agent.context_manager = None
    agent.model_manager = None
    agent.agent_slot = "main"

    state = {
        "messages": [{"role": "user", "content": "Добавь URL"}],
        "step_count": 0,
        "conversation_id": "tg_admin_1",
        "stream": False,
        "user_input": "Добавь URL",
        "tool_results": [],
        "honesty_nudge_count": 0,
        "plan_steps": [],
        "current_plan_step": 0,
    }
    config = {"configurable": {"_agent": agent}}

    with (
        patch.object(rn, "profile_name_from_agent", return_value="admin"),
        patch.object(rn, "_build_system_prompt_from_state", return_value="sys"),
        patch.object(
            rn,
            "_compress_messages_if_needed",
            new_callable=AsyncMock,
            return_value=(state["messages"], {}),
        ),
        patch.object(rn, "_llm_max_tokens", return_value=512),
        patch.object(rn, "resolve_usage", return_value={"prompt_tokens": 1, "completion_tokens": 1}),
        patch.object(rn, "usage_dict_from_response", return_value=None),
        patch.object(rn, "emit_llm_call_usage"),
        patch.object(rn, "completion_text_from_message", return_value=message.content),
        # Force honesty not to swallow so we reach the deferred-final return.
        patch.object(rn, "_maybe_honesty_retry", return_value=None),
        patch.object(rn, "plan_step_active", return_value=False),
    ):
        result = await rn.react_node(state, config)

    assert result.get("is_final") is True
    assert result.get("final_response")
    finals = [
        c.args[0]
        for c in agent.emit.call_args_list
        if c.args and isinstance(c.args[0], FinalResponseEvent)
    ]
    assert finals == [], "draft must not emit FinalResponseEvent before graph end"
