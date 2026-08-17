"""Static + runtime classification of one-shot jobs vs services."""

from __future__ import annotations

import asyncio
import sys

import pytest
from core.runtime.service_detect import (
    is_long_oneshot_job,
    is_untracked_long_running_command,
    should_promote_foreground_service,
)
from core.tools.terminal import (
    PromoteForegroundService,
    _communicate_with_cancel,
    _kill_process_tree,
    _promote_label,
)


def test_oneshot_jobs_are_not_launches() -> None:
    oneshots = [
        "cargo test --all",
        "cargo build --release",
        "go test ./...",
        "go build ./cmd/api",
        "mvn -q test",
        "mvn -pl api test",
        "mvn package",
        "./gradlew test",
        "dotnet test",
        "dotnet restore && dotnet build",
        "cmake --build build",
        "g++ main.cpp -o app",
        "pytest -q",
        "python -m pytest tests",
        "npm run build",
        "make test",
    ]
    for cmd in oneshots:
        assert is_long_oneshot_job(cmd) is True, cmd
        assert is_untracked_long_running_command(cmd) is False, cmd


def test_unknown_binary_is_not_a_static_launch() -> None:
    """C++/custom binaries cannot be classified by regex — runtime decides."""
    for cmd in ("./target/release/api", "./build/server --port 8080", "bin/holix-api"):
        assert is_untracked_long_running_command(cmd) is False, cmd
        assert is_long_oneshot_job(cmd) is False, cmd


def test_promote_requires_listen_and_elapsed() -> None:
    cmd = "./target/release/api --port 8080"
    ok, ports = should_promote_foreground_service(cmd, pid=1, elapsed_s=10, listen_ports=[8080])
    assert ok is False
    assert ports == []

    ok, ports = should_promote_foreground_service(cmd, pid=1, elapsed_s=61, listen_ports=[8080])
    assert ok is True
    assert ports == [8080]

    ok, ports = should_promote_foreground_service(cmd, pid=1, elapsed_s=120, listen_ports=[])
    assert ok is False


def test_promote_skips_oneshot_even_if_port_bound() -> None:
    """pytest / cargo test may bind a fixture port — leave them in the foreground."""
    ok, ports = should_promote_foreground_service(
        "cargo test",
        pid=1,
        elapsed_s=180,
        listen_ports=[54321],
    )
    assert ok is False
    assert ports == []

    ok, _ = should_promote_foreground_service(
        "python -m pytest tests",
        pid=1,
        elapsed_s=180,
        listen_ports=[8000],
    )
    assert ok is False


def test_promote_label_uses_first_token() -> None:
    assert _promote_label("java -jar app.jar") == "java"
    assert _promote_label("") == "promoted-service"


@pytest.mark.asyncio
async def test_communicate_promotes_when_tree_listens(monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_SERVICE_WATCH_AFTER", "0.15")
    monkeypatch.setenv("HOLIX_SERVICE_WATCH_INTERVAL", "0.05")
    monkeypatch.setattr(
        "core.tools.terminal.listen_ports_for_pid_tree",
        lambda pid: [8080],
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time; time.sleep(8)",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        with pytest.raises(PromoteForegroundService) as exc:
            await _communicate_with_cancel(
                process,
                timeout=3,
                command="./target/release/api",
            )
        assert exc.value.ports == [8080]
    finally:
        await _kill_process_tree(process)


@pytest.mark.asyncio
async def test_communicate_does_not_promote_oneshot(monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_SERVICE_WATCH_AFTER", "0.1")
    monkeypatch.setenv("HOLIX_SERVICE_WATCH_INTERVAL", "0.05")
    monkeypatch.setattr(
        "core.tools.terminal.listen_ports_for_pid_tree",
        lambda pid: [8080],
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time; time.sleep(8)",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        with pytest.raises(TimeoutError):
            await _communicate_with_cancel(
                process,
                timeout=0.35,
                command="cargo test --all",
            )
    finally:
        await _kill_process_tree(process)


@pytest.mark.asyncio
async def test_communicate_does_not_promote_without_listen(monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_SERVICE_WATCH_AFTER", "0.1")
    monkeypatch.setenv("HOLIX_SERVICE_WATCH_INTERVAL", "0.05")
    monkeypatch.setattr(
        "core.tools.terminal.listen_ports_for_pid_tree",
        lambda pid: [],
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time; time.sleep(8)",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        with pytest.raises(TimeoutError):
            await _communicate_with_cancel(
                process,
                timeout=0.35,
                command="./long-train-job",
            )
    finally:
        await _kill_process_tree(process)
