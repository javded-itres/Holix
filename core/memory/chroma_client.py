"""Process-wide Chroma ``PersistentClient`` cache.

Chroma 0.5+/1.x rust bindings (``chromadb_rust_bindings``) segfault when the
same process opens more than one ``PersistentClient`` on one directory.
Holix used to construct one client in ``ConversationStore`` and another in
``VectorMemoryStore`` for the same ``vector_db_path``, then more for extra
Studio sessions and in-process sub-agents — that kills the Studio process
(Caddy 502) as soon as SDD apply spawns parallel sub-agents.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_CLIENTS: dict[str, Any] = {}


def chroma_client_key(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())


def get_persistent_client(path: str | Path, **kwargs: Any) -> Any:
    """Return the process singleton PersistentClient for ``path``."""
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    key = chroma_client_key(path)
    with _LOCK:
        client = _CLIENTS.get(key)
        if client is not None:
            return client
        settings = kwargs.pop("settings", None) or ChromaSettings(anonymized_telemetry=False)
        client = chromadb.PersistentClient(path=key, settings=settings, **kwargs)
        _CLIENTS[key] = client
        return client


def reset_persistent_clients() -> None:
    """Drop cached clients (tests). Does not shut down native Chroma runtimes."""
    with _LOCK:
        _CLIENTS.clear()
