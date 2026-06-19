"""Cross-platform helpers for paths, processes, and shell hints."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
IS_POSIX = os.name == "posix"

_CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _legacy_helix_home() -> Path | None:
    """Return ~/.helix when present and ~/.holix is not (pre-rebrand data dir)."""
    holix = Path.home() / ".holix"
    helix = Path.home() / ".helix"
    if helix.is_dir() and not holix.is_dir():
        return helix.resolve()
    return None


def resolve_holix_home() -> Path:
    """Holix data directory (HOLIX_HOME, HELIX_HOME legacy, XDG, or ~/.holix)."""
    if raw := os.environ.get("HOLIX_HOME", "").strip():
        return Path(raw).expanduser().resolve()
    if raw := os.environ.get("HELIX_HOME", "").strip():
        return Path(raw).expanduser().resolve()
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return (Path(base) / "Holix").resolve()
        if legacy := _legacy_helix_home():
            return legacy
        return (Path.home() / ".holix").resolve()
    if xdg := os.environ.get("XDG_DATA_HOME", "").strip():
        return (Path(xdg) / "holix").resolve()
    if legacy := _legacy_helix_home():
        return legacy
    return (Path.home() / ".holix").resolve()


def holix_home_display() -> str:
    return str(resolve_holix_home())


def process_subagents_supported() -> bool:
    """OS-process sub-agents are reliable on POSIX; Windows uses async fallback."""
    return not IS_WINDOWS


def prefer_async_subagents() -> bool:
    """Use in-process async sub-agents when OS-process spawn is unreliable."""
    if os.environ.get("HOLIX_SUBAGENT_ASYNC", "").strip().lower() in {"1", "true", "yes"}:
        return True
    if os.environ.get("HOLIX_SUBAGENT_PROCESS", "").strip().lower() in {"1", "true", "yes"}:
        return False
    # Piped / detached hosts (TUI web, IDE runners, tmux wrappers) often hit fds_to_keep.
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return True
    return False


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        # Windows: signal 0 is unsupported; WinError 87 means the PID is invalid.
        return False
    return True


def _kill_signal(pid: int, sig: int) -> None:
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        pass


def _psutil_terminate_tree(pid: int, *, force: bool) -> bool:
    try:
        import psutil
    except ImportError:
        return False

    try:
        proc = psutil.Process(pid)
    except psutil.Error:
        return False

    children = proc.children(recursive=True)
    targets = children + [proc]
    if force:
        for p in targets:
            try:
                p.kill()
            except psutil.Error:
                pass
        psutil.wait_procs(targets, timeout=5)
        return True

    for p in targets:
        try:
            p.terminate()
        except psutil.Error:
            pass
    _gone, alive = psutil.wait_procs(targets, timeout=5)
    for p in alive:
        try:
            p.kill()
        except psutil.Error:
            pass
    return True


def _windows_terminate(pid: int, *, force: bool) -> None:
    args = ["taskkill", "/PID", str(pid), "/T"]
    if force:
        args.append("/F")
    try:
        subprocess.run(args, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        sig = getattr(signal, "SIGKILL", signal.SIGTERM) if force else signal.SIGTERM
        _kill_signal(pid, sig)


def terminate_process(pid: int, *, grace: float = 10.0) -> None:
    """Gracefully stop a process (and its group on POSIX)."""
    if not is_process_alive(pid):
        return

    if _psutil_terminate_tree(pid, force=False):
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            if not is_process_alive(pid):
                return
            time.sleep(0.2)
        _psutil_terminate_tree(pid, force=True)
        return

    if IS_POSIX and hasattr(os, "killpg") and hasattr(os, "getpgid"):
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except ProcessLookupError:
            return
        except OSError:
            _kill_signal(pid, signal.SIGTERM)
    elif IS_WINDOWS:
        _windows_terminate(pid, force=False)
    else:
        _kill_signal(pid, signal.SIGTERM)

    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not is_process_alive(pid):
            return
        time.sleep(0.2)

    if IS_WINDOWS:
        _windows_terminate(pid, force=True)
    elif IS_POSIX and hasattr(os, "killpg") and hasattr(os, "getpgid"):
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            _kill_signal(pid, signal.SIGKILL)
    else:
        _kill_signal(pid, signal.SIGKILL)


def _validate_subprocess_argv(cmd: list[str]) -> list[str]:
    if not cmd or not all(isinstance(arg, str) and arg for arg in cmd):
        raise ValueError("Invalid subprocess command")
    if any("\0" in arg for arg in cmd):
        raise ValueError("Invalid subprocess command")
    return list(cmd)


def _resolve_background_executable(program: str) -> str:
    resolved = shutil.which(program)
    if not resolved:
        raise ValueError(f"Command not found: {program}")
    return resolved


def popen_background(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    stdout=None,
    stderr=None,
    stdin=None,
    cwd: str | None = None,
) -> subprocess.Popen:
    """Spawn a detached background child process."""
    argv = _validate_subprocess_argv(cmd)
    executable = _resolve_background_executable(argv[0])
    safe_argv = [executable, *argv[1:]]
    kwargs: dict = {
        "env": env,
        "stdout": stdout,
        "stderr": stderr,
        "stdin": stdin if stdin is not None else subprocess.DEVNULL,
        "shell": False,
    }
    if cwd is not None:
        kwargs["cwd"] = cwd
    if IS_POSIX:
        kwargs["start_new_session"] = True
        kwargs["close_fds"] = True
    elif IS_WINDOWS and _CREATE_NEW_PROCESS_GROUP:
        kwargs["creationflags"] = _CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(safe_argv, **kwargs)


def port_check_hint(port: int) -> str:
    if IS_WINDOWS:
        return f"netstat -ano | findstr :{port}"
    if IS_MACOS:
        return f"lsof -i :{port}"
    return f"ss -ltnp | grep :{port}  # or: lsof -i :{port}"


def psutil_available() -> bool:
    try:
        import psutil  # noqa: F401

        return True
    except ImportError:
        return False


def subprocess_shell_kwargs() -> dict:
    """Extra kwargs for asyncio/subprocess shell spawns (hide console on Windows)."""
    if IS_WINDOWS and _CREATE_NO_WINDOW:
        return {"creationflags": _CREATE_NO_WINDOW}
    return {}


def clipboard_tools_available() -> bool:
    import shutil

    if IS_WINDOWS:
        return shutil.which("clip") is not None or shutil.which("powershell") is not None
    if IS_MACOS:
        return True
    return any(shutil.which(name) for name in ("wl-copy", "xclip", "xsel"))


def ensure_multiprocessing_support() -> None:
    """Required on Windows before spawning multiprocessing children."""
    import multiprocessing

    multiprocessing.freeze_support()