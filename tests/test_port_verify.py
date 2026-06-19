"""Tests for port listener verification."""

from __future__ import annotations

from unittest.mock import patch

from core.runtime.background_process_health import apply_port_checks, build_health_report
from core.runtime.port_verify import (
    PortCheckResult,
    PortListenerInfo,
    listener_owned_by_process,
    verify_expected_ports,
)


def test_listener_owned_by_child_pid() -> None:
    with patch("core.runtime.port_verify._pid_in_process_tree", return_value=True):
        assert listener_owned_by_process(
            5555,
            root_pid=1111,
            root_running=True,
            expected_command="npm run dev",
            listener_command="node vite",
        )


def test_verify_foreign_listener() -> None:
    with patch(
        "core.runtime.port_verify.describe_port_listeners",
        return_value=[PortListenerInfo(port=8000, pid=9999, command="other-server")],
    ), patch(
        "core.runtime.port_verify.listener_owned_by_process",
        return_value=False,
    ):
        checks = verify_expected_ports(
            expected_ports=[8000],
            root_pid=1111,
            root_running=True,
            expected_command="uvicorn app:app --port 8000",
        )
    assert checks[0].issue == "foreign_listener"
    assert checks[0].owned_by_process is False


def test_apply_port_checks_sets_wrong_process_status() -> None:
    base = build_health_report(
        process_id="p1",
        label="api",
        pid=100,
        log_path="/tmp/x.log",
        running=True,
        exit_code=None,
        log_tail="INFO starting",
    )
    checks = [
        PortCheckResult(
            port=8000,
            listener_pids=[9999],
            listener_commands=["foreign"],
            owned_by_process=False,
            issue="foreign_listener",
        )
    ]
    merged = apply_port_checks(base, port_checks=checks, expected_ports=[8000])
    assert merged.status == "wrong_process_on_port"
    assert "restart_background_process" in merged.recommendation
    text = merged.format_text()
    assert "port listeners:" in text
    assert "foreign" in text