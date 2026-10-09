"""Process-wide Chroma ``PersistentClient`` cache.

Chroma 0.5+/1.x rust bindings (``chromadb_rust_bindings``) segfault when the
same process opens more than one ``PersistentClient`` on one directory.
Holix used to construct one client in ``ConversationStore`` and another in
``VectorMemoryStore`` for the same ``vector_db_path``, then more for extra
Studio sessions and in-process sub-agents — that kills the Studio process
(Caddy 502) as soon as SDD apply spawns parallel sub-agents.

The same library also segfaults when a second *process* (the TUI, while the
gateway already has the profile index open) calls into that directory. An
exclusive lock plus a check for an existing holder keeps the second process
out of the native client.
"""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_CLIENTS: dict[str, Any] = {}
_LOCK_FDS: dict[str, int] = {}


class ChromaDirectoryBusy(RuntimeError):
    """Another process already has this on-disk Chroma directory open."""


def chroma_client_key(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())


def _foreign_holder_pids(directory: Path) -> list[int]:
    """Pids other than ours that already have this Chroma directory open.

    A gateway started before this lock existed still holds ``chroma.sqlite3``.
    Opening another native client on that file crashes the process.
    """
    sqlite = directory / "chroma.sqlite3"
    target = sqlite if sqlite.is_file() else directory
    if not target.exists():
        return []
    try:
        proc = subprocess.run(
            ["lsof", "-t", "--", str(target)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    me = os.getpid()
    pids: list[int] = []
    for line in (proc.stdout or "").splitlines():
        text = line.strip()
        if not text.isdigit():
            continue
        pid = int(text)
        if pid != me and pid not in pids:
            pids.append(pid)
    return pids


def _release_lock(key: str) -> None:
    fd = _LOCK_FDS.pop(key, None)
    if fd is None:
        return
    if os.name == "posix":
        import fcntl

        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
    try:
        os.close(fd)
    except OSError:
        pass


def _acquire_directory_lock(directory: Path) -> int | None:
    """Hold an exclusive lock for the life of this process, or report busy."""
    if os.name != "posix":
        return None
    import fcntl

    directory.mkdir(parents=True, exist_ok=True)
    fd = os.open(directory / ".holix-chroma.lock", os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise ChromaDirectoryBusy(str(directory)) from None
    return fd


def get_persistent_client(path: str | Path, **kwargs: Any) -> Any:
    """Return the process singleton PersistentClient for ``path``.

    Raises ``ChromaDirectoryBusy`` when another process already owns the
    directory. Callers must keep chat on SQLite and skip the native index.
    """
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    key = chroma_client_key(path)
    with _LOCK:
        client = _CLIENTS.get(key)
        if client is not None:
            return client
        directory = Path(key)
        fd = _acquire_directory_lock(directory)
        foreign = _foreign_holder_pids(directory)
        if foreign:
            if fd is not None:
                import fcntl

                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
                os.close(fd)
            raise ChromaDirectoryBusy(f"{key} held by {foreign}")
        if fd is not None:
            _LOCK_FDS[key] = fd
        try:
            settings = kwargs.pop("settings", None) or ChromaSettings(anonymized_telemetry=False)
            client = chromadb.PersistentClient(path=key, settings=settings, **kwargs)
        except Exception:
            _release_lock(key)
            raise
        _CLIENTS[key] = client
        return client


def reset_persistent_clients() -> None:
    """Drop cached clients (tests). Does not shut down native Chroma runtimes."""
    with _LOCK:
        for key in list(_LOCK_FDS):
            _release_lock(key)
        _CLIENTS.clear()
