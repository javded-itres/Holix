"""Live LLM: same-agent background tasks (not sub-agents)."""

from __future__ import annotations

import asyncio

import pytest
from core.runtime.agent_tasks import format_agent_task_wakeup, get_agent_task_registry

from tests.live_llm.provider import soft_contains

pytestmark = [pytest.mark.live_llm, pytest.mark.llm]

_MARKER = "BG_LIVE_72"


def _skip_unreliable(result) -> None:
    low = result.text.lower()
    if "timed out" in low or "connection error" in low:
        pytest.skip(f"provider timeout: {result.text[:160]}")
    if result.looks_unreliable():
        pytest.skip(f"unreliable live reply: {result.text[:160]}")


def _started_task_id(result) -> str | None:
    for payload in result.tool_payloads("run_terminal_command"):
        raw = ""
        if isinstance(payload, dict):
            raw = str(payload.get("raw") or payload.get("error") or "")
        else:
            raw = str(payload)
        if "Background task started:" not in raw or "id=" not in raw:
            continue
        token = raw.split("id=", 1)[1].split()[0].strip(" .,")
        if token.startswith("task_"):
            return token
    return None


async def _wait_task(task_id: str, timeout: float = 20.0):
    registry = get_agent_task_registry()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        task = registry.get(task_id)
        if task is not None and not task.is_running():
            return task
        await asyncio.sleep(0.05)
    return registry.get(task_id)


@pytest.mark.asyncio
async def test_live_72_background_task_wakes_with_output(live_harness):
    """Model starts a finite command in the background, then reports its output."""
    registry = get_agent_task_registry()
    registry.clear()
    try:
        started = await live_harness.run(
            "You MUST call run_terminal_command exactly once with these arguments and no others:\n"
            f"- command: echo {_MARKER}\n"
            "- background: true\n"
            "- description: live background marker\n"
            "Do not wait for the process. After the tool returns, reply in one sentence "
            "that the background task was started and include its task id. "
            "Do not call list_agent_tasks, start_background_process, or a sub-agent.",
            conversation_id="live_72",
            timeout_s=300,
        )
        _skip_unreliable(started)
        assert started.called("run_terminal_command"), (
            f"expected run_terminal_command, got {started.tool_names()}; {started.text[:400]}"
        )
        task_id = _started_task_id(started)
        assert task_id, (
            "run_terminal_command did not start a background task. "
            f"payloads={started.tool_payloads('run_terminal_command')!r}"
        )
        task = await _wait_task(task_id)
        assert task is not None, task_id
        assert task.status == "completed", (task.status, task.exit_code, task.output)
        assert _MARKER in task.output

        reported = await live_harness.run(
            format_agent_task_wakeup(task),
            conversation_id="live_72",
            timeout_s=240,
        )
        _skip_unreliable(reported)
        assert soft_contains(reported.text, _MARKER, "background", "finished", min_hits=1), (
            reported.text[:500]
        )
    finally:
        registry.clear()
