"""Terminal result formatting: pipefail and red pytest behind a pipe."""

from __future__ import annotations

from core.runtime.terminal_result import format_process_result, with_pipefail
from core.runtime.test_run_signals import failure_snippet, is_test_log_dump


def test_with_pipefail_prefixes_once() -> None:
    cmd = "pytest -q | tail -20"
    wrapped = with_pipefail(cmd)
    assert "set -o pipefail" in wrapped or wrapped == cmd
    assert "BASH_VERSION" in wrapped or wrapped == cmd
    assert with_pipefail(wrapped) == wrapped


def test_pipefail_prefix_is_legal_on_posix_sh() -> None:
    import shutil
    import subprocess

    from core.platform_compat import IS_WINDOWS

    if IS_WINDOWS:
        return
    sh = shutil.which("sh")
    if not sh:
        return
    wrapped = with_pipefail("echo ok && echo chained")
    result = subprocess.run(
        [sh, "-c", wrapped],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
    assert "chained" in result.stdout
    assert "Illegal option" not in (result.stderr or "")


def test_pytest_failed_output_is_error_even_when_rc_zero() -> None:
    out = (
        "Success (exit code 0):\n"
        "src/foo.py::test_paid FAILED\n"
        "=========================== short test summary info ===========================\n"
        "FAILED src/foo.py::test_paid - IntegrityError\n"
    )
    # strip the fake Success header — formatter sees raw stdout
    raw = (
        "src/foo.py::test_paid FAILED\n"
        "=========================== short test summary info ===========================\n"
        "FAILED src/foo.py::test_paid - IntegrityError\n"
    )
    text = format_process_result(
        returncode=0,
        output=raw,
        error="",
        command="cd backend && pytest -q 2>&1 | tail -60",
    )
    assert text.startswith("Error (exit code 0, tests failed")
    assert "FAILED" in text
    assert is_test_log_dump(out)
    assert "IntegrityError" in failure_snippet(raw)


def test_green_pytest_still_success() -> None:
    raw = "........\n8 passed in 0.37s"
    text = format_process_result(
        returncode=0,
        output=raw,
        command="pytest -q",
    )
    assert text.startswith("Success (exit code 0)")


def test_non_test_failed_word_not_flipped() -> None:
    raw = "failed to bind port 8000"
    text = format_process_result(
        returncode=0,
        output=raw,
        command="curl -s http://127.0.0.1:8000/health",
    )
    assert text.startswith("Success (exit code 0)")
