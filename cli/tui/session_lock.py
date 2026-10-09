"""Keep two TUI windows off the same conversation and off one shared state file."""

from __future__ import annotations

import os
from pathlib import Path

from core.platform_compat import resolve_holix_home


def sessions_dir() -> Path:
    return resolve_holix_home() / "tui-sessions"


def window_id() -> str:
    raw = (os.environ.get("HOLIX_TUI_WINDOW") or "").strip()
    if raw:
        return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in raw)[:80]
    return str(os.getpid())


def window_state_path() -> Path:
    return sessions_dir() / f"{window_id()}.json"


def _lock_file(conversation_id: str) -> str | None:
    """Lock path under the sessions directory. Reject anything that escapes it."""
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in conversation_id)[:120]
    if not safe:
        safe = "_"
    root = os.path.realpath(sessions_dir() / "locks")
    os.makedirs(root, exist_ok=True)
    candidate = os.path.realpath(os.path.join(root, f"{safe}.lock"))
    if not candidate.startswith(root + os.sep):
        return None
    return candidate


def pid_alive(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_lock_pid(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return 0


def conversation_busy(conversation_id: str) -> bool:
    """True when another live TUI window already holds this conversation."""
    if not (conversation_id or "").strip():
        return False
    path = _lock_file(conversation_id)
    if path is None:
        return False
    pid = _read_lock_pid(Path(path))
    return pid_alive(pid)


def _exclusive(fd: int) -> None:
    """Block until this process holds the lock file. Windows has no fcntl."""
    try:
        import fcntl
    except ModuleNotFoundError:
        return
    fcntl.flock(fd, fcntl.LOCK_EX)


def _holder(fd: int) -> int:
    os.lseek(fd, 0, os.SEEK_SET)
    raw = os.read(fd, 64).decode("utf-8", "replace").strip()
    try:
        return int(raw or "0")
    except ValueError:
        return 0


def claim_conversation(conversation_id: str) -> bool:
    """Record this process as the owner. A live other owner keeps the conversation.

    The file stays in place. Releasing it clears the pid while the lock is held,
    so a second window cannot create a replacement that this process then deletes.
    """
    if not (conversation_id or "").strip():
        return False
    path = _lock_file(conversation_id)
    if path is None:
        return False
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        _exclusive(fd)
        if pid_alive(_holder(fd)):
            return False
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.fsync(fd)
        return True
    finally:
        os.close(fd)


def release_conversation(conversation_id: str) -> None:
    if not (conversation_id or "").strip():
        return
    path = _lock_file(conversation_id)
    if path is None:
        return
    try:
        fd = os.open(path, os.O_RDWR)
    except OSError:
        return
    try:
        _exclusive(fd)
        if _holder(fd) == os.getpid():
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
