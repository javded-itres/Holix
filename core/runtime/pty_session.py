"""Persistent POSIX PTY shell per conversation (cwd and env stick)."""

from __future__ import annotations

import asyncio
import os
import re
import secrets
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any

from core.platform_compat import IS_POSIX, IS_WINDOWS

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

_DONE = "__HOLIX_DONE__"
_READY = "__HOLIX_READY__"
_MAX_SESSIONS = 8
_DRAIN_CAP = 2_000_000


class PtyUnavailable(RuntimeError):
    """Host cannot keep a persistent PTY (Windows, disabled, or spawn failed)."""


@dataclass
class PtyResult:
    returncode: int
    output: str
    cwd: str


def pty_env_enabled() -> bool:
    if not IS_POSIX or IS_WINDOWS:
        return False
    raw = os.environ.get("HOLIX_PTY", "").strip().lower()
    if raw in {"0", "off", "false", "no"}:
        return False
    return True


_lock = threading.Lock()
_sessions: dict[tuple[str, str], PtyShell] = {}
_disabled: set[tuple[str, str]] = set()


def _key(profile: str, conversation_id: str) -> tuple[str, str]:
    return (
        (profile or "default").strip() or "default",
        (conversation_id or "default").strip() or "default",
    )


def pty_enabled(*, profile: str, conversation_id: str) -> bool:
    if not pty_env_enabled():
        return False
    with _lock:
        return _key(profile, conversation_id) not in _disabled


def set_pty_enabled(profile: str, conversation_id: str, enabled: bool) -> None:
    key = _key(profile, conversation_id)
    with _lock:
        if enabled:
            _disabled.discard(key)
        else:
            _disabled.add(key)
    if not enabled:
        close_pty(profile, conversation_id)


def pty_status(profile: str, conversation_id: str) -> str:
    key = _key(profile, conversation_id)
    enabled = pty_enabled(profile=profile, conversation_id=conversation_id)
    with _lock:
        shell = _sessions.get(key)
    if not enabled:
        return "pty: off (one-shot commands)"
    if shell is None or not shell.alive:
        backend = "posix PTY (idle — next command starts a shell)"
        return f"pty: on\nbackend: {backend}"
    return f"pty: on\npid: {shell.pid}\ncwd: {shell.cwd}\nbackend: posix PTY"


def close_pty(profile: str, conversation_id: str) -> None:
    key = _key(profile, conversation_id)
    with _lock:
        shell = _sessions.pop(key, None)
    if shell is not None:
        shell.close()


def reset_pty_sessions() -> None:
    with _lock:
        shells = list(_sessions.values())
        _sessions.clear()
        _disabled.clear()
    for shell in shells:
        shell.close()


def _evict_if_needed(keep: tuple[str, str]) -> None:
    with _lock:
        if len(_sessions) < _MAX_SESSIONS:
            return
        victims = [k for k in _sessions if k != keep]
        if not victims:
            return
        key = victims[0]
        shell = _sessions.pop(key, None)
    if shell is not None:
        shell.close()


class PtyShell:
    def __init__(self, proc: subprocess.Popen[Any], master_fd: int, cwd: str) -> None:
        self.proc = proc
        self.master_fd = master_fd
        self.cwd = cwd
        self._io = asyncio.Lock()

    @property
    def pid(self) -> int:
        return int(self.proc.pid or 0)

    @property
    def alive(self) -> bool:
        return self.proc.poll() is None

    def close(self) -> None:
        try:
            if self.proc.poll() is None and self.pid:
                try:
                    os.killpg(self.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    self.proc.terminate()
        except Exception:
            pass
        try:
            os.close(self.master_fd)
        except OSError:
            pass
        try:
            self.proc.wait(timeout=1)
        except Exception:
            try:
                if self.pid:
                    os.killpg(self.pid, signal.SIGKILL)
            except Exception:
                pass

    def _write_once(self, view: memoryview) -> int:
        try:
            return os.write(self.master_fd, view)
        except InterruptedError:
            return 0
        except BlockingIOError:
            return 0

    def _read_chunk(self) -> bytes:
        try:
            return os.read(self.master_fd, 8192)
        except (BlockingIOError, InterruptedError):
            return b""
        except OSError:
            return b""

    def _drain(self, buf: bytearray) -> None:
        while len(buf) < _DRAIN_CAP:
            chunk = self._read_chunk()
            if not chunk:
                return
            buf.extend(chunk)

    def _write_sync(self, data: str, *, timeout: float) -> bytearray:
        """Write to a non-blocking PTY; drain output so the slave cannot deadlock."""
        view = memoryview(data.encode("utf-8"))
        drained = bytearray()
        deadline = time.monotonic() + max(timeout, 0.5)
        while view:
            if time.monotonic() >= deadline:
                raise TimeoutError
            n = self._write_once(view)
            self._drain(drained)
            if n:
                view = view[n:]
                continue
            time.sleep(0.02)
        return drained

    async def _write(self, data: str, *, timeout: float) -> bytearray:
        view = memoryview(data.encode("utf-8"))
        drained = bytearray()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(timeout, 0.5)
        while view:
            if loop.time() >= deadline:
                raise TimeoutError
            n = self._write_once(view)
            self._drain(drained)
            if n:
                view = view[n:]
                continue
            await asyncio.sleep(0.02)
        return drained

    async def _read_until(
        self,
        pattern: re.Pattern[bytes],
        timeout: float,
        initial: bytes | bytearray = b"",
    ) -> str:
        loop = asyncio.get_running_loop()
        buf = bytearray(initial)
        if pattern.search(buf):
            self._drain(buf)
            return buf.decode("utf-8", errors="replace")
        deadline = loop.time() + timeout
        while True:
            if self.proc.poll() is not None:
                extra = self._read_chunk()
                if extra:
                    buf.extend(extra)
                break
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError
            chunk = await asyncio.to_thread(self._read_chunk)
            if chunk:
                buf.extend(chunk)
                if pattern.search(buf):
                    self._drain(buf)
                    return buf.decode("utf-8", errors="replace")
            else:
                await asyncio.sleep(0.02)
        if pattern.search(buf):
            self._drain(buf)
            return buf.decode("utf-8", errors="replace")
        raise EOFError(buf.decode("utf-8", errors="replace"))

    async def run(self, command: str, *, timeout: float) -> PtyResult:
        async with self._io:
            token = secrets.token_hex(16)
            wrapped = _wrap_command(command, token)
            done_re = re.compile(rf"{re.escape(_DONE)} {re.escape(token)} (\d+)\|".encode())
            drained = await self._write(wrapped, timeout=timeout)
            raw = await self._read_until(done_re, timeout, initial=drained)
            parsed = _parse_done(raw, token, fallback_cwd=self.cwd)
            self.cwd = parsed.cwd
            return parsed


def _wrap_command(command: str, token: str) -> str:
    delim = f"HOLIXEOF{token[:16]}"
    body = command.replace("\r\n", "\n").rstrip("\n")
    return (
        f"set +e\n"
        f"eval \"$(cat <<'{delim}'\n"
        f"{body}\n"
        f"{delim}\n"
        f')"\n'
        f"_holix_st=$?\n"
        f'printf \'\\n{_DONE} {token} %s|%s\\n\' "$_holix_st" "$(pwd)"\n'
    )


def _parse_done(raw: str, token: str, *, fallback_cwd: str) -> PtyResult:
    marker = f"{_DONE} {token} "
    idx = raw.rfind(marker)
    output = raw[:idx] if idx >= 0 else raw
    tail = raw[idx + len(marker) :] if idx >= 0 else "0|" + fallback_cwd
    line = tail.splitlines()[0] if tail else f"0|{fallback_cwd}"
    status_s, _, pwd = line.partition("|")
    try:
        code = int(status_s.strip())
    except ValueError:
        code = 1
    cwd = pwd.strip() or fallback_cwd
    # Drop echoed control lines / empty leading noise
    cleaned = output.replace("\r", "")
    cleaned = re.sub(rf"(?m)^.*{_READY}.*\n?", "", cleaned)
    kept: list[str] = []
    for line in cleaned.splitlines():
        if line.startswith(("set +e", 'eval "$(cat', "stty -echo", "_holix_st=", "printf ")):
            continue
        if line.startswith("HOLIXEOF"):
            continue
        kept.append(line)
    cleaned = "\n".join(kept)
    return PtyResult(returncode=code, output=cleaned.strip("\n"), cwd=cwd)


def _spawn_shell(
    *,
    cwd: str,
    workspace_root: str | None,
    sandbox_mode: str,
) -> PtyShell:
    if fcntl is None:
        raise PtyUnavailable("PTY requires POSIX fcntl")
    import pty as py_pty

    bash = shutil.which("bash") or "/bin/bash"
    argv = [bash, "--noprofile", "--norc"]
    env = os.environ.copy()
    env["PS1"] = ""
    env["PS2"] = ""
    env["TERM"] = "dumb"
    if sandbox_mode != "danger-full-access":
        from core.security.os_sandbox import confine_argv

        env["HOLIX_SANDBOX"] = sandbox_mode
        argv = confine_argv(argv, mode=sandbox_mode, workspace_root=workspace_root, cwd=cwd)
    master_fd, slave_fd = py_pty.openpty()
    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    try:
        proc = subprocess.Popen(
            argv,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=cwd,
            env=env,
            start_new_session=True,
            close_fds=True,
        )
    finally:
        try:
            os.close(slave_fd)
        except OSError:
            pass
    shell = PtyShell(proc, master_fd, cwd)
    try:
        shell._write_sync(
            "unset PROMPT_COMMAND; PS1=; PS2=; stty -echo 2>/dev/null || true; "
            f"printf '{_READY}\\n'\n",
            timeout=5.0,
        )
    except Exception:
        shell.close()
        raise
    return shell


async def _ensure_ready(shell: PtyShell, timeout: float = 5.0) -> None:
    try:
        await shell._read_until(re.compile(re.escape(_READY).encode()), timeout)
    except (TimeoutError, EOFError):
        if not shell.alive:
            raise PtyUnavailable("PTY shell exited during startup") from None


async def run_in_pty(
    command: str,
    *,
    timeout: float,
    cwd: str | None,
    workspace_root: str | None,
    jail_enabled: bool,
    profile: str,
    conversation_id: str,
) -> str:
    from core.memory.tool_content import truncate_terminal_output
    from core.security.permission_preset import sandbox_mode_for_session
    from core.workspace import sanitize_paths_in_text

    if not pty_enabled(profile=profile, conversation_id=conversation_id):
        raise PtyUnavailable("PTY disabled")
    start_cwd = cwd or os.getcwd()
    mode = sandbox_mode_for_session(profile, conversation_id, jail_enabled=jail_enabled)
    key = _key(profile, conversation_id)
    _evict_if_needed(key)
    with _lock:
        shell = _sessions.get(key)
        if shell is not None and not shell.alive:
            _sessions.pop(key, None)
            shell.close()
            shell = None
    if shell is None:
        shell = _spawn_shell(cwd=start_cwd, workspace_root=workspace_root, sandbox_mode=mode)
        await _ensure_ready(shell)
        with _lock:
            _sessions[key] = shell
    from core.runtime.terminal_result import with_pipefail

    command = with_pipefail(command)
    try:
        result = await shell.run(command, timeout=timeout)
    except TimeoutError:
        close_pty(profile, conversation_id)
        return f"Error: Command timed out after {int(timeout)} seconds (PTY reset)"
    except EOFError:
        close_pty(profile, conversation_id)
        return "Error: PTY shell exited unexpectedly"
    shell.cwd = result.cwd
    output = truncate_terminal_output(sanitize_paths_in_text(result.output))
    from core.runtime.terminal_result import format_process_result

    return format_process_result(
        returncode=int(result.returncode or 0),
        output=output,
        error="",
        command=command,
    )
