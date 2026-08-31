"""Format shell tool results; honor pytest failures even when a pipe hid rc."""

from __future__ import annotations

from core.platform_compat import IS_WINDOWS
from core.runtime.test_run_signals import is_red_test_output, is_test_command, is_test_log_dump


def with_pipefail(command: str) -> str:
    """Prefix POSIX shells so ``pytest | tail`` keeps pytest's exit code."""
    text = str(command or "")
    if not text.strip() or IS_WINDOWS:
        return text
    stripped = text.lstrip()
    if stripped.startswith("set -o pipefail"):
        return text
    return "set -o pipefail; " + text


def format_process_result(
    *,
    returncode: int,
    output: str,
    error: str = "",
    command: str = "",
) -> str:
    """Human-readable terminal tool payload.

    ``pytest … | tail`` often returns 0 because ``tail`` succeeded. If the
    combined output still looks like a red test run, report Error.
    """
    out = output or ""
    err = error or ""
    blob = f"{out}\n{err}"
    rc = int(returncode or 0)
    tests_lied_ok = (
        rc == 0
        and bool(command)
        and is_test_command(command)
        and (is_red_test_output(blob) or is_test_log_dump(blob))
    )
    if tests_lied_ok:
        body = out if out.strip() else err
        return f"Error (exit code 0, tests failed in output):\n{body}"
    if rc == 0:
        return f"Success (exit code 0):\n{out}" if out else "Success (no output)"
    return f"Error (exit code {rc}):\nSTDOUT:\n{out}\nSTDERR:\n{err}"
