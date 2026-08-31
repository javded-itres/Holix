"""Library-introspection loops are not implementation progress."""

from __future__ import annotations

import time

import pytest
from core.runtime.introspect_signals import (
    INTROSPECT_REFUSAL,
    introspect_loop,
    is_introspect_code,
    is_introspect_command,
)
from core.runtime.step_budget import StepBudgetPolicy, evaluate_step_budget
from core.subagents.base import SubAgentConfig, SubAgentHandle, SubAgentStatus
from core.subagents.supervisor import assess_handle


def _cmd(method: str) -> str:
    return (
        '{"command": "cd projects/data_address && python -c \\"'
        f"from dadata.asynchr import DadataClient; import inspect; "
        f"print(inspect.getsource(DadataClient.{method}))"
        '\\""}'
    )


def test_detects_inspect_getsource() -> None:
    assert is_introspect_command('python -c "import inspect; print(inspect.getsource(Foo.bar))"')
    assert is_introspect_command('python -c "print(dir(app))"')
    assert is_introspect_command(
        'python -c "import dadata; print(dadata.Dadata.__init__.__code__.co_flags)"'
    )
    assert not is_introspect_command('python -c "import dadata; print(dadata.Dadata.__name__)"')
    assert not is_introspect_command('python -c "import json; print(1)"')
    assert not is_introspect_command("python -m pytest tests")
    assert not is_introspect_command("pip install dadata")
    assert not is_introspect_command('python -c "print(1)"')
    assert not is_introspect_code(
        "try:\n    1/0\nexcept ZeroDivisionError as e:\n    print(type(e).__name__)"
    )
    assert "dadata" not in INTROSPECT_REFUSAL.lower()


def test_introspect_loop_on_rotating_methods() -> None:
    traces = [
        {"name": "terminal", "arguments": _cmd(name)}
        for name in ("close", "suggest", "find_by_id", "geolocate")
    ]
    assert introspect_loop(traces) is True


def test_introspect_loop_false_when_write_started() -> None:
    traces = [
        {"name": "terminal", "arguments": _cmd("suggest")},
        {"name": "terminal", "arguments": _cmd("geolocate")},
        {"name": "terminal", "arguments": _cmd("close")},
        {"name": "write_file", "arguments": '{"path": "app/main.py"}'},
        {"name": "terminal", "arguments": _cmd("iplocate")},
    ]
    assert introspect_loop(traces) is False


def test_supervisor_flags_inspect_rotation_as_loop() -> None:
    h = SubAgentHandle(
        name="coder",
        config=SubAgentConfig(name="coder", max_steps=50),
        status=SubAgentStatus.RUNNING,
        started_at=time.monotonic(),
        max_steps=50,
    )
    h.touch_activity()
    h.last_tool = "terminal"
    h.config.tools = ["read_file", "write_file", "terminal"]
    h.steps_taken = 20
    for method in ("close", "suggest", "find_by_id", "get_balance", "iplocate"):
        h.record_activity(
            "tool_start",
            "Calling terminal",
            tool_name="terminal",
            details=_cmd(method),
        )
        h.record_activity(
            "tool_result",
            "terminal finished",
            tool_name="terminal",
            details="Success (exit code 0):\n    async def ...",
        )
    d = assess_handle(h)
    assert d.kind == "loop"
    assert d.signals.get("inspect_loop") is True
    assert "write_file" in d.guidance
    assert "inspect" in d.guidance.lower()


def test_step_budget_does_not_extend_on_inspect_loop() -> None:
    log = [
        {
            "name": "terminal",
            "arguments": _cmd(name),
            "result": "Success (exit code 0):\n    async def foo",
        }
        for name in ("close", "suggest", "find_by_id", "geolocate")
    ]
    d = evaluate_step_budget(
        step_count=150,
        max_steps=150,
        tool_calls_log=log,
        task="сделать fastapi каталог адресов",
        policy=StepBudgetPolicy(extend_by=30, max_extensions=3),
        base_max_steps=90,
    )
    assert not d.extend
    assert d.status == "hung"
    assert "inspect" in d.reason.lower()


@pytest.mark.asyncio
async def test_terminal_refuses_python_c_library_probe() -> None:
    from core.tools.terminal import TerminalTool

    out = await TerminalTool().execute(
        'cd projects/data_address && python -c "import inspect; from dadata.asynchr import DadataClient; print(inspect.getsource(DadataClient.suggest))"',
        timeout=5,
    )
    assert "write_file" in out
    assert "Success" not in out
    assert "DaDataAsync" not in out
