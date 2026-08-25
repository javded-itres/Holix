"""Persistent PTY shell: cwd and env survive across commands."""

from __future__ import annotations

import pytest
from core.platform_compat import IS_POSIX
from core.runtime.pty_session import (
    PtyUnavailable,
    pty_status,
    reset_pty_sessions,
    run_in_pty,
    set_pty_enabled,
)

pytestmark = pytest.mark.skipif(not IS_POSIX, reason="PTY is POSIX-only")


@pytest.fixture(autouse=True)
def _pty_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_PTY", "1")
    reset_pty_sessions()
    yield
    reset_pty_sessions()


async def _run(command: str, tmp_path, *, cid: str = "s1") -> str:
    return await run_in_pty(
        command,
        timeout=15.0,
        cwd=str(tmp_path),
        workspace_root=str(tmp_path),
        jail_enabled=False,
        profile="test",
        conversation_id=cid,
    )


@pytest.mark.asyncio
async def test_pty_cd_persists(tmp_path) -> None:
    sub = tmp_path / "nested"
    sub.mkdir()
    first = await _run("cd nested && pwd", tmp_path)
    assert "nested" in first
    second = await _run("pwd", tmp_path)
    assert "nested" in second


@pytest.mark.asyncio
async def test_pty_export_persists(tmp_path) -> None:
    await _run("export HOLIX_PTY_PROBE=ok", tmp_path)
    out = await _run('printf "%s" "$HOLIX_PTY_PROBE"', tmp_path)
    assert "ok" in out


@pytest.mark.asyncio
async def test_pty_disable_raises(tmp_path) -> None:
    set_pty_enabled("test", "off1", False)
    with pytest.raises(PtyUnavailable):
        await _run("pwd", tmp_path, cid="off1")
    assert "off" in pty_status("test", "off1")


@pytest.mark.asyncio
async def test_pty_nonzero_exit(tmp_path) -> None:
    out = await _run("false", tmp_path)
    assert "exit code" in out.lower()
    assert "1" in out


@pytest.mark.asyncio
async def test_pty_write_retries_blocking_ioerror(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-blocking PTY EAGAIN must sleep/retry, not spin the event loop."""
    import os

    await _run("true", tmp_path)
    calls = {"n": 0}
    real_write = os.write

    def flaky(fd: int, data: object, *args: object, **kwargs: object) -> int:
        calls["n"] += 1
        if calls["n"] <= 4:
            raise BlockingIOError
        return real_write(fd, data)

    monkeypatch.setattr(os, "write", flaky)
    out = await _run("printf ok", tmp_path)
    assert "ok" in out
    assert calls["n"] > 4


@pytest.mark.asyncio
async def test_pty_large_command_and_output(tmp_path) -> None:
    payload = "z" * 50_000
    out = await _run(f"printf '%s' '{payload}' | wc -c", tmp_path)
    assert "50000" in out.replace(" ", "")
    big = await _run("python3 -c \"print('x'*20000, end='')\"", tmp_path)
    assert big.count("x") >= 20_000
