"""ReAct node LLM step timeout."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.graph.nodes.react_node import _DEFAULT_LLM_STEP_TIMEOUT_S, _llm_step_timeout_s, react_node


@pytest.mark.asyncio
async def test_react_node_streaming_timeout_emits_final_error() -> None:
    async def _slow_stream():
        await asyncio.sleep(60)
        if False:  # pragma: no cover
            yield None

    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_slow_stream())

    agent = MagicMock()
    agent.client = client
    agent.model = "slow-model"
    agent.tools.get_schemas.return_value = []
    agent.config = SimpleNamespace(
        subagent_process_timeout=0.05,
        profile_name="default",
    )
    agent.model_manager = None
    agent.context_manager = None
    agent.emit = MagicMock()

    state = {
        "step_count": 0,
        "conversation_id": "test",
        "stream": True,
        "messages": [],
    }
    config = {"configurable": {"_agent": agent}}

    result = await react_node(state, config)

    assert result["is_final"] is True
    assert "не ответила" in result["final_response"]
    final_events = [
        call.args[0]
        for call in agent.emit.call_args_list
        if call.args and call.args[0].__class__.__name__ == "FinalResponseEvent"
    ]
    assert final_events
    assert "не ответила" in final_events[-1].content


def test_llm_step_timeout_default() -> None:
    assert _llm_step_timeout_s(None) == _DEFAULT_LLM_STEP_TIMEOUT_S