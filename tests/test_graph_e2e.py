"""LangGraph ReAct E2E with mocked LLM (no live provider)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.agent import HelixAgent
from core.agent_events import EventType
from core.di.runtime_config import HelixRuntimeConfig
from core.graph.builder import build_helix_graph, prepare_initial_state
from core.persistence import create_checkpointer


def _mock_llm_response(content: str = "Graph mock answer.", tool_calls=None):
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    response = MagicMock()
    response.choices = [MagicMock(message=message)]
    return response


@pytest.mark.integration
@pytest.mark.asyncio
async def test_react_graph_completes_with_mock_llm(temp_dir):
    """ReAct graph: memory_retrieval → react → finalize yields final response."""
    cfg = HelixRuntimeConfig.from_settings().with_overrides(
        memory_db_path=f"{temp_dir}/mem.db",
        vector_db_path=f"{temp_dir}/vec",
        ltm_db_path=f"{temp_dir}/ltm.db",
        skills_dir=f"{temp_dir}/skills",
        enable_long_term_memory=False,
        use_langgraph=True,
        non_interactive=True,
    )
    agent = HelixAgent(config=cfg, enable_monitoring=False)

    agent.memory.get_conversation = AsyncMock(return_value=[])
    agent.memory.save_message = AsyncMock()
    agent.memory.search = AsyncMock(return_value=[])
    agent.skills.get_relevant_skills = MagicMock(return_value=[])
    agent.skills.format_skills_for_prompt = MagicMock(return_value="")
    agent.tools.get_schemas = MagicMock(return_value=[])
    agent.client.chat.completions.create = AsyncMock(
        return_value=_mock_llm_response("E2E graph completed successfully.")
    )

    graph = build_helix_graph(
        agent=agent,
        execution_mode="react",
        checkpointer=create_checkpointer(use_persistent=False),
        stream=False,
    )

    state = prepare_initial_state(
        agent, "Hello graph", "e2e_conv", execution_mode="react"
    )
    state["messages"] = []

    config = {
        "configurable": {
            "thread_id": "e2e_conv",
            "_agent": agent,
        },
    }

    agent.begin_run("e2e_conv")
    final_state = await graph.ainvoke(state, config)
    agent.end_run()

    assert final_state.get("is_final") is True
    assert "E2E graph" in (final_state.get("final_response") or "")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_helix_graph_path_yields_events(temp_dir, monkeypatch):
    """run_helix (graph branch) emits thinking events with run_id correlation."""
    from core.runtime.executor import run_helix

    cfg = HelixRuntimeConfig.from_settings().with_overrides(
        memory_db_path=f"{temp_dir}/mem.db",
        vector_db_path=f"{temp_dir}/vec",
        ltm_db_path=f"{temp_dir}/ltm.db",
        skills_dir=f"{temp_dir}/skills",
        enable_long_term_memory=False,
        non_interactive=True,
        plan_review_enabled=False,
    )
    agent = HelixAgent(config=cfg, enable_monitoring=False)
    await agent.initialize()

    agent.memory.get_conversation = AsyncMock(return_value=[])
    agent.memory.save_message = AsyncMock()
    agent.memory.search = AsyncMock(return_value=[])
    agent.skills.get_relevant_skills = MagicMock(return_value=[])
    agent.skills.format_skills_for_prompt = MagicMock(return_value="")
    agent.tools.get_schemas = MagicMock(return_value=[])
    agent.client.chat.completions.create = AsyncMock(
        return_value=_mock_llm_response("Helix unified runtime OK.")
    )

    monkeypatch.setattr(
        "core.graph.builder.create_checkpointer",
        lambda **kwargs: create_checkpointer(use_persistent=False),
    )

    collected = []
    async for event in run_helix(agent, "ping", "run_helix_e2e", stream=False):
        collected.append(event)

    types = {e.type for e in collected}
    assert EventType.THINKING in types
    stamped = [e for e in collected if getattr(e, "run_id", "")]
    assert stamped and all(e.run_id for e in stamped)