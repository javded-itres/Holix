"""Tool output truncation helpers."""

from __future__ import annotations

from core.memory.tool_content import strip_debug_log_lines, truncate_terminal_output


def test_strip_debug_log_lines_drops_aiosqlite_noise() -> None:
    raw = (
        "Success (exit code 0):\n"
        "DEBUG    aiosqlite:core.py:62 executing functools.partial(rollback)\n"
        "DEBUG    aiosqlite:core.py:67 operation completed\n"
        "FAILED src/tests/test_bot_payment.py::test_successful_payment_handler_issues_key\n"
        "AssertionError: payload\n"
    )
    out = strip_debug_log_lines(raw)
    assert "aiosqlite" not in out
    assert "AssertionError: payload" in out
    assert "omitted" in out


def test_truncate_terminal_output_strips_debug_first() -> None:
    raw = "DEBUG    x\n" * 100 + "1 failed\n"
    out = truncate_terminal_output(raw, max_chars=2000)
    assert "1 failed" in out
    assert "DEBUG    x" not in out
