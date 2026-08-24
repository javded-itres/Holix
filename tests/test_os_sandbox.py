"""OS filesystem sandbox wrapping and fail-closed behavior."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from core.security.os_sandbox import (
    SandboxUnavailable,
    confine_argv,
    normalize_sandbox_mode,
    sandbox_backend,
)


def test_normalize_sandbox_mode() -> None:
    assert normalize_sandbox_mode("workspace_write") == "workspace-write"
    assert normalize_sandbox_mode("danger") == "danger-full-access"
    assert normalize_sandbox_mode("ro") == "read-only"


def test_danger_does_not_wrap() -> None:
    argv = ["/bin/echo", "ok"]
    assert confine_argv(argv, mode="danger-full-access", workspace_root="/tmp") == argv


def test_restricted_without_backend_fail_closed(monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_OS_SANDBOX", "0")
    with pytest.raises(SandboxUnavailable):
        confine_argv(["/bin/echo", "x"], mode="workspace-write", workspace_root="/tmp")


def test_wrap_prefixes_backend_when_available(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HOLIX_OS_SANDBOX", raising=False)
    backend = sandbox_backend()
    if backend is None:
        pytest.skip("no OS sandbox backend on this host")
    ws = tmp_path / "ws"
    ws.mkdir()
    wrapped = confine_argv(
        ["/bin/echo", "hi"],
        mode="workspace-write",
        workspace_root=str(ws),
        cwd=str(ws),
    )
    assert wrapped[0] in {"sandbox-exec", "bwrap"}
    assert "hi" in wrapped


@pytest.mark.skipif(sandbox_backend() is None, reason="no OS sandbox backend")
def test_workspace_write_blocks_outside_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    probe = "/etc/holix-sandbox-probe"
    wrapped = confine_argv(
        ["/bin/bash", "-lc", f"echo pwned > {probe}"],
        mode="workspace-write",
        workspace_root=str(ws),
        cwd=str(ws),
    )
    subprocess.run(wrapped, cwd=str(ws), check=False, capture_output=True)
    assert not Path(probe).exists()
    inside = ws / "ok.txt"
    wrapped_ok = confine_argv(
        ["/bin/bash", "-lc", "echo yes > ok.txt"],
        mode="workspace-write",
        workspace_root=str(ws),
        cwd=str(ws),
    )
    subprocess.run(wrapped_ok, cwd=str(ws), check=False, capture_output=True)
    assert inside.read_text(encoding="utf-8").strip() == "yes"
