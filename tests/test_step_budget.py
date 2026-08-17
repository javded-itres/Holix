"""Tests for step-budget health check and auto-extension."""

from __future__ import annotations

from core.runtime.step_budget import (
    StepBudgetPolicy,
    evaluate_step_budget,
    maybe_extend_for_graph_result,
)


def test_not_at_limit_no_extend() -> None:
    d = evaluate_step_budget(step_count=10, max_steps=90)
    assert not d.extend
    assert d.status == "not_at_limit"


def test_extend_when_pending_tools_and_progress() -> None:
    messages = [
        {"role": "user", "content": "Implement auth module"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "write_file",
                        "arguments": '{"path":"auth.py"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "1",
            "content": "OK: wrote auth.py successfully with login handlers",
        },
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "2",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path":"auth.py"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "2",
            "content": "def login(): ... found existing helpers",
        },
    ]
    d = evaluate_step_budget(
        step_count=90,
        max_steps=90,
        pending_tool_calls=[{"id": "3", "function": {"name": "run_terminal_command"}}],
        messages=messages,
        task="Implement auth module",
        policy=StepBudgetPolicy(extend_by=30, max_extensions=3),
        base_max_steps=90,
    )
    assert d.extend
    assert d.status == "working"
    assert d.new_max_steps == 120
    assert d.extensions_used == 1


def test_identical_tool_loop_detects_mid_run() -> None:
    from core.runtime.step_budget import identical_tool_loop

    log = [
        {"name": "terminal", "arguments": '{"command": "inspect"}', "result": "79"},
        {"name": "terminal", "arguments": '{"command": "inspect"}', "result": "79"},
    ]
    assert identical_tool_loop(log) is False
    log.append({"name": "terminal", "arguments": '{"command": "inspect"}', "result": "79"})
    assert identical_tool_loop(log) is True


def test_hung_on_identical_tool_loop() -> None:
    log = [
        {"name": "run_terminal_command", "arguments": "ls", "result": "Error: fail"},
        {"name": "run_terminal_command", "arguments": "ls", "result": "Error: fail"},
        {"name": "run_terminal_command", "arguments": "ls", "result": "Error: fail"},
    ]
    d = evaluate_step_budget(
        step_count=50,
        max_steps=50,
        pending_tool_calls=[{"id": "x"}],
        tool_calls_log=log,
        task="list files",
        policy=StepBudgetPolicy(),
    )
    assert not d.extend
    assert d.status == "hung"
    assert "loop" in d.reason.lower()


def test_no_extend_when_same_pytest_already_green() -> None:
    log = [
        {
            "name": "terminal",
            "arguments": '{"command": "python -m pytest -q"}',
            "result": "Success (exit code 0): 8 passed in 0.37s",
        },
        {
            "name": "grep",
            "arguments": '{"pattern": "def test_", "path": "tests"}',
            "result": "8 match(es) in 3 file(s)",
        },
        {
            "name": "terminal",
            "arguments": '{"command": "python -m pytest -q"}',
            "result": "Success (exit code 0): 8 passed in 0.38s",
        },
    ]
    d = evaluate_step_budget(
        step_count=150,
        max_steps=150,
        extensions_used=0,
        pending_tool_calls=[{"id": "x"}],
        tool_calls_log=log,
        task="fix the review comments",
        policy=StepBudgetPolicy(extend_by=30, max_extensions=10),
        base_max_steps=150,
    )
    assert not d.extend
    assert "tests already passed" in d.reason


def test_no_extend_on_noop_write_loop() -> None:
    log = [
        {
            "name": "write_file",
            "arguments": '{"path": "app/ioc.py"}',
            "result": "Updated app/ioc.py (no content changes)",
        },
        {
            "name": "write_file",
            "arguments": '{"path": "app/application/use_cases.py"}',
            "result": "Updated app/application/use_cases.py (no content changes)",
        },
        {
            "name": "write_file",
            "arguments": '{"path": "app/ioc.py"}',
            "result": "Updated app/ioc.py (no content changes)",
        },
    ]
    d = evaluate_step_budget(
        step_count=150,
        max_steps=150,
        tool_calls_log=log,
        task="fastapi address catalog",
        policy=StepBudgetPolicy(extend_by=30, max_extensions=3),
        base_max_steps=90,
    )
    assert not d.extend
    assert d.status == "hung"
    assert "no content" in d.reason.lower()


def test_extension_cap() -> None:
    d = evaluate_step_budget(
        step_count=150,
        max_steps=150,
        extensions_used=3,
        pending_tool_calls=[{"id": "1"}],
        tool_calls_log=[
            {"name": "write_file", "arguments": "a", "result": "OK written successfully"},
            {"name": "read_file", "arguments": "b", "result": "content found here"},
        ],
        task="write code",
        policy=StepBudgetPolicy(max_extensions=3),
        base_max_steps=90,
    )
    assert not d.extend
    assert "extension limit" in d.reason


def test_graph_result_extends_max_steps() -> None:
    state = {
        "user_input": "Build a REST API",
        "max_steps": 15,
        "base_max_steps": 15,
        "step_budget_extensions": 0,
        "conversation_id": "t1",
        "messages": [
            {"role": "user", "content": "Build a REST API"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "1",
                        "function": {
                            "name": "write_file",
                            "arguments": '{"path":"api.py"}',
                        },
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
        "tool_calls": [{"id": "2", "function": {"name": "read_file"}}],
        "is_final": False,
        "messages": state["messages"],
    }
    out = maybe_extend_for_graph_result(state, result, agent=None, task="Build a REST API")
    assert out["max_steps"] > 15
    assert out["step_budget_extensions"] == 1


def test_graph_result_no_extend_when_final() -> None:
    state = {"max_steps": 15, "user_input": "hi"}
    result = {"step_count": 15, "is_final": True, "tool_calls": []}
    out = maybe_extend_for_graph_result(state, result, agent=None)
    assert (
        out is result
        or out.get("max_steps") is None
        or "max_steps" not in out
        or out.get("step_count") == 15
    )
    assert out.get("max_steps", 15) == 15 or "step_budget_extensions" not in out
