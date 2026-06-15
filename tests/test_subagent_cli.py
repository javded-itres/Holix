"""CLI sub-agent helpers and commands."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.config_utils import is_subagents_enabled


def test_is_subagents_enabled_defaults_true() -> None:
    assert is_subagents_enabled(None) is True
    assert is_subagents_enabled(SimpleNamespace()) is True
    assert is_subagents_enabled(SimpleNamespace(enable_subagents=None)) is True


def test_is_subagents_enabled_respects_false() -> None:
    assert is_subagents_enabled(SimpleNamespace(enable_subagents=False)) is False


def test_is_subagents_enabled_respects_true() -> None:
    assert is_subagents_enabled(SimpleNamespace(enable_subagents=True)) is True


@pytest.mark.asyncio
async def test_deliver_subagent_result_on_timeout() -> None:
    from cli.shared.commands.subagent_commands import _deliver_subagent_result_when_ready

    class Handle:
        class Config:
            timeout = 1.0

        config = Config()
        status = type("S", (), {"value": "timed_out"})()

    class Mgr:
        def get_handle(self, _name: str):
            return Handle()

        async def wait_for(self, _name: str, timeout: float | None = None):
            raise TimeoutError()

    class Agent:
        subagents = Mgr()

    writes: list[str] = []

    class Host:
        agent = Agent()

        def transcript_write(self, text: object) -> None:
            writes.append(str(text))

    await _deliver_subagent_result_when_ready(Host(), "coder")
    assert writes and "timed out" in writes[0].lower()


@pytest.mark.asyncio
async def test_resolve_agent_waits_for_host_init() -> None:
    from cli.shared.commands.subagent_commands import _resolve_agent

    host = SimpleNamespace(agent=None, _agent_init_state="initializing")

    async def _finish() -> None:
        import asyncio

        await asyncio.sleep(0.35)
        host.agent = object()
        host._agent_init_state = "ready"

    import asyncio

    waiter = asyncio.create_task(_finish())
    agent = await _resolve_agent(host, wait_timeout=2.0)
    await waiter
    assert agent is host.agent