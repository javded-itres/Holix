"""Select Chroma, pgvector, or in-memory vector storage for the Holix agent."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.memory.vector_protocol import VectorBackend

logger = logging.getLogger(__name__)

Embedder = Callable[[list[str]], list[list[float]]]

_PG_CACHE: dict[tuple[str, str, str, int], VectorBackend] = {}
_PG_LOCK = threading.Lock()


def normalize_vector_backend(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in {"pgvector", "postgres", "postgresql", "pg"}:
        return "pgvector"
    if value in {"memory", "inmemory", "in-memory"}:
        return "memory"
    return "chroma"


def _normalize_dsn(url: str) -> str:
    u = (url or "").strip()
    if u.startswith("postgresql+psycopg://"):
        return "postgresql://" + u[len("postgresql+psycopg://") :]
    if u.startswith("postgres://"):
        return "postgresql://" + u[len("postgres://") :]
    return u


def is_postgres_dsn(url: str | None) -> bool:
    parsed = urlparse(_normalize_dsn(url or ""))
    return parsed.scheme in {"postgres", "postgresql"}


def resolve_vector_dsn(cfg: Any | None = None) -> str:
    candidates = []
    if cfg is not None:
        candidates.append(str(getattr(cfg, "vector_dsn", "") or ""))
    candidates.extend(
        [
            os.environ.get("HOLIX_VECTOR_DSN") or "",
            os.environ.get("HOLIX_VECTOR_DATABASE_URL") or "",
            os.environ.get("VECTOR_DSN") or "",
            os.environ.get("STUDIO_DATABASE_URL") or "",
        ]
    )
    for raw in candidates:
        dsn = _normalize_dsn(raw)
        if is_postgres_dsn(dsn):
            return dsn
    return ""


def resolve_vector_backend_name(cfg: Any | None = None) -> str:
    raw = ""
    if cfg is not None:
        raw = str(getattr(cfg, "vector_backend", "") or "")
    if not raw:
        raw = os.environ.get("HOLIX_VECTOR_BACKEND") or os.environ.get("VECTOR_BACKEND") or ""
    if not raw:
        try:
            from config import Settings

            raw = str(getattr(Settings(_env_file=None), "vector_backend", "") or "")
        except Exception:
            raw = ""
    return normalize_vector_backend(raw)


def uses_on_disk_chroma(cfg: Any | None = None) -> bool:
    return resolve_vector_backend_name(cfg) == "chroma"


def hash_embedder(dim: int) -> Embedder:
    size = max(int(dim), 1)

    def _embed(texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256((text or "").encode("utf-8")).digest()
            vec = [((digest[i % len(digest)] / 255.0) * 2.0) - 1.0 for i in range(size)]
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out

    return _embed


def default_embedder() -> Embedder:
    from core.memory.chroma_embeddings import embed_documents

    return embed_documents


def open_vector_backend(
    cfg: Any | None = None,
    *,
    chroma_path: str | Path | None = None,
    embedder: Embedder | None = None,
) -> VectorBackend:
    """Return the process vector backend for this config.

    ``chroma_path`` selects the on-disk Chroma directory (conversation vs skills).
    pgvector ignores it and namespaces by collection name + profile.
    """
    from core.di.runtime_config import HolixRuntimeConfig

    config = cfg or HolixRuntimeConfig.from_settings()
    name = resolve_vector_backend_name(config)
    dim = int(getattr(config, "vector_dim", 384) or 384)
    fn = embedder or (hash_embedder(dim) if name == "memory" else default_embedder())

    if name == "memory":
        from core.memory.memory_vector import InMemoryVectorBackend

        return InMemoryVectorBackend(fn)

    if name == "pgvector":
        dsn = resolve_vector_dsn(config)
        if not dsn:
            raise RuntimeError(
                "HOLIX_VECTOR_BACKEND=pgvector requires HOLIX_VECTOR_DSN or STUDIO_DATABASE_URL"
            )
        try:
            import psycopg  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "pgvector backend needs psycopg (pip install 'psycopg[binary]')"
            ) from exc
        profile = str(getattr(config, "profile_name", "") or "default")
        table = str(getattr(config, "vector_table", "") or "holix_vectors")
        key = (dsn, profile, table, dim)
        with _PG_LOCK:
            cached = _PG_CACHE.get(key)
            if cached is not None:
                return cached
            from core.memory.pgvector_store import PgVectorBackend

            backend = PgVectorBackend(
                dsn=dsn,
                profile=profile,
                dim=dim,
                table=table,
                embedder=fn,
            )
            _PG_CACHE[key] = backend
            logger.info(
                "Holix vector backend=pgvector profile=%s table=%s dim=%s",
                profile,
                table,
                dim,
            )
            return backend

    from core.memory.chroma_vector import ChromaVectorBackend

    path = chroma_path if chroma_path is not None else getattr(config, "vector_db_path", None)
    if not path:
        path = "data/memory/vector_db"
    return ChromaVectorBackend(path)
