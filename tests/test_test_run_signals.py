"""Green-test detection: do not treat re-running passing pytest as work."""

from __future__ import annotations

from core.runtime.test_run_signals import (
    is_green_test_output,
    is_test_command,
    tests_already_green_loop,
)


def test_pytest_command_and_green_output() -> None:
    assert is_test_command("cd app && python -m pytest -q --cache-clear")
    assert is_test_command("pytest tests/test_api.py")
    assert not is_test_command("python -m data_address.main")
    assert is_green_test_output("Success (exit code 0):\n........\n8 passed in 0.37s")
    assert not is_green_test_output("2 passed, 1 failed in 0.2s")
    assert not is_green_test_output("Error: Command timed out after 15 seconds")


def test_green_loop_after_second_pytest() -> None:
    traces = [
        {
            "name": "terminal",
            "arguments": '{"command": "python -m pytest -q"}',
            "result": "8 passed in 0.3s",
        },
        {
            "name": "grep",
            "arguments": '{"pattern": "def test_", "path": "tests"}',
            "result": "8 match(es)",
        },
        {
            "name": "terminal",
            "arguments": '{"command": "python -m pytest -q"}',
            "result": "8 passed in 0.3s",
        },
    ]
    assert tests_already_green_loop(traces) is True


def test_single_green_pytest_then_grep_tests_is_loop() -> None:
    traces = [
        {
            "name": "terminal",
            "arguments": '{"command": "pytest -q"}',
            "result": "3 passed in 0.1s",
        },
        {
            "name": "grep",
            "arguments": '{"pattern": "def test_", "path": "projects/app/tests"}',
            "result": "3 match(es)",
        },
    ]
    assert tests_already_green_loop(traces) is True
