"""P2 surface user cases: slash commands + gateway chat completions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from api.models import ChatCompletionRequest, Message
from api.routers.legacy_v1 import chat_completions
from cli.shared.commands.agent_commands import AgentCommands
from core.gateway.locks import GatewayLocks

from tests.user_cases.fake_host import FakeAgentHost
from tests.user_cases.scripted_llm import Final, ToolCall


@pytest.mark.user_case
@pytest.mark.integration
@pytest.mark.asyncio
async def test_uc21_slash_mode_and_status(harness):
    """UC-21: /mode sets execution mode; /status reports profile + mode + confirm policy."""
    host = FakeAgentHost(
        agent=harness.agent,
        profile="default",
        conversation_id="uc21",
        execution_mode_index=0,  # react
    )
    cmds = AgentCommands(host)

    await cmds.handle("/mode plan_and_execute")
    assert host.current_mode == "plan_and_execute"
    assert host.status_refreshes >= 1
    mode_text = host.transcript_text()
    assert "plan_and_execute" in mode_text

    host.transcript.clear()
    await cmds.handle("/status")
    status = host.transcript_text()
    assert "default" in status  # profile
    assert "plan_and_execute" in status
    assert "auto_allow" in status or "confirmations" in status
    # harness default is high auto-allow
    assert "high" in status


@pytest.mark.user_case
@pytest.mark.integration
@pytest.mark.asyncio
async def test_uc21_slash_mode_cycle(harness):
    """UC-21b: bare /mode cycles to the next mode."""
    host = FakeAgentHost(agent=harness.agent, execution_mode_index=0)
    cmds = AgentCommands(host)
    assert host.current_mode == "react"

    await cmds.handle("/mode")
    assert host.current_mode == "plan_and_execute"
    assert "plan_and_execute" in host.transcript_text() or "mode →" in host.transcript_text()


@pytest.mark.user_case
@pytest.mark.integration
@pytest.mark.asyncio
async def test_uc20_gateway_chat_completions_real_agent(harness, monkeypatch):
    """UC-20: OpenAI-compat chat completions path runs real agent + tools."""
    harness.workspace.write("README.md", "# Holix\nGateway surface\n")
    harness.script(
        [
            ToolCall("read_file", {"path": "README.md"}),
            Final("Gateway saw Holix README."),
        ]
    )
    assert harness.agent is not None

    registry = MagicMock()
    registry.get_agent = AsyncMock(return_value=harness.agent)

    request = ChatCompletionRequest(
        model="default",
        messages=[Message(role="user", content="Read README and summarize")],
        conversation_id="uc20_gateway",
    )

    import api.state

    monkeypatch.setattr(
        api.state, "_agent_request_lock", __import__("asyncio").Lock(), raising=False
    )

    response = await chat_completions(
        locks=GatewayLocks(),
        registry=registry,
        host_profile="default",
        request=request,
        key_info={"permissions": ["read", "write", "execute"]},
        x_holix_profile=None,
        x_hermes_profile=None,
        x_holix_session_id=None,
        x_hermes_session_id=None,
    )

    content = response.choices[0]["message"]["content"]
    assert "Holix" in content or "Gateway" in content
    harness.llm.assert_exhausted()
    # Side effect path: tool executed under jail
    # (no JourneyResult — surface returns HTTP body; assert workspace still intact)
    assert harness.workspace.exists("README.md")
