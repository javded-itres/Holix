"""Continue/Abort pause when the main-agent step budget is exhausted."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from core.agent_events import StepBudgetChoiceEvent
from core.presenters.final_content import (
    coerce_usable_final_text,
    is_code_or_diff_dump,
    step_limit_reached_message,
)
from core.runtime.step_budget import StepBudgetPolicy, maybe_extend_or_ask
from core.runtime.step_budget_pause import (
    ABORT,
    CONTINUE,
    ask_continue_or_abort,
    can_ask_user,
    resolve_step_budget,
)


class _Bus:
    def __init__(self) -> None:
        self.events: list[object] = []

    def emit(self, event: object) -> None:
        self.events.append(event)


class _Agent:
    def __init__(self, *, non_interactive: bool = False) -> None:
        self.events = _Bus()
        self.config = SimpleNamespace(
            non_interactive=non_interactive,
            profile_name="default",
            max_steps_extend_by=30,
            max_steps_user_max_extensions=10,
            max_steps_max_extensions=10,
            max_steps_extend_enabled=True,
        )
        self.subagent_system_prompt = None

    def emit(self, event: object) -> None:
        self.events.emit(event)


def test_code_or_diff_dump_detection() -> None:
    diff = (
        "diff --git a/foo.py b/foo.py\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,3 +1,8 @@\n"
        "+def run():\n"
        "+    return 1\n"
    ) * 8
    assert is_code_or_diff_dump(diff)
    assert not is_code_or_diff_dump("Updated foo.py and ran tests. All 8 passed.")
    assert "Достигнут лимит шагов" in coerce_usable_final_text(diff, max_steps=90)
    assert "90" in step_limit_reached_message(90, step_count=90, extra_steps=30, locale="en")


def test_can_ask_user_skips_subagents_and_unattended() -> None:
    policy = StepBudgetPolicy(user_max_extensions=10)
    main = _Agent()
    assert can_ask_user(main, conversation_id="studio_tab", user_used=0, policy=policy)
    sub = _Agent()
    sub.subagent_system_prompt = "You are a coder sub-agent"
    assert not can_ask_user(sub, conversation_id="subagent:job", user_used=0, policy=policy)
    quiet = _Agent(non_interactive=True)
    assert not can_ask_user(quiet, conversation_id="cron", user_used=0, policy=policy)
    assert not can_ask_user(main, conversation_id="studio_tab", user_used=10, policy=policy)


@pytest.mark.asyncio
async def test_ask_continue_resolves_future() -> None:
    agent = _Agent()

    async def _resolve() -> None:
        await asyncio.sleep(0)
        ev = next(e for e in agent.events.events if isinstance(e, StepBudgetChoiceEvent))
        assert ev.request_id
        assert any(c.get("code") == CONTINUE for c in ev.choices)
        assert resolve_step_budget(ev.request_id, CONTINUE)

    task = asyncio.create_task(_resolve())
    choice = await ask_continue_or_abort(
        agent=agent,
        conversation_id="c1",
        step_count=90,
        max_steps=90,
        extra_steps=30,
        user_used=0,
        user_max=10,
        reason="extension limit reached",
        locale="en",
    )
    await task
    assert choice == CONTINUE


@pytest.mark.asyncio
async def test_maybe_extend_or_ask_user_continue() -> None:
    agent = _Agent()
    state = {
        "user_input": "Build a REST API",
        "max_steps": 15,
        "base_max_steps": 15,
        "step_budget_extensions": 10,
        "step_budget_user_extensions": 0,
        "conversation_id": "t1",
        "messages": [
            {"role": "user", "content": "Build a REST API"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "1",
                        "function": {"name": "write_file", "arguments": '{"path":"api.py"}'},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "1",
                "content": "OK: created api.py with endpoints successfully",
            },
        ],
    }
    result = {
        "step_count": 15,
        "max_steps": 15,
        "is_final": True,
        "final_response": "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@\n" + ("+x\n" * 20),
        "tool_calls": [],
        "messages": state["messages"],
        "step_budget_extensions": 10,
    }

    async def _resolve() -> None:
        for _ in range(50):
            await asyncio.sleep(0)
            ev = next(
                (e for e in agent.events.events if isinstance(e, StepBudgetChoiceEvent)),
                None,
            )
            if ev is not None:
                resolve_step_budget(ev.request_id, CONTINUE)
                return
        raise AssertionError("no StepBudgetChoiceEvent")

    task = asyncio.create_task(_resolve())
    out = await maybe_extend_or_ask(state, result, agent=agent, task="Build a REST API")
    await task
    assert out["max_steps"] == 45
    assert out.get("is_final") is False
    assert out.get("step_budget_user_extensions") == 1


@pytest.mark.asyncio
async def test_maybe_extend_or_ask_abort() -> None:
    agent = _Agent()
    state = {
        "max_steps": 15,
        "step_budget_extensions": 10,
        "conversation_id": "t1",
        "user_input": "hi",
        "messages": [],
    }
    result = {
        "step_count": 15,
        "max_steps": 15,
        "is_final": False,
        "final_response": "",
        "tool_calls": [],
        "messages": [],
        "step_budget_extensions": 10,
    }

    async def _resolve() -> None:
        for _ in range(50):
            await asyncio.sleep(0)
            ev = next(
                (e for e in agent.events.events if isinstance(e, StepBudgetChoiceEvent)),
                None,
            )
            if ev is not None:
                resolve_step_budget(ev.request_id, ABORT)
                return
        raise AssertionError("no StepBudgetChoiceEvent")

    task = asyncio.create_task(_resolve())
    out = await maybe_extend_or_ask(state, result, agent=agent, task="hi")
    await task
    assert out.get("is_final") is True
    text = str(out.get("final_response") or "").lower()
    assert "15" in text
    assert "limit" in text or "лимит" in text
    assert out.get("max_steps") == 15
