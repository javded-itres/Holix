"""PostgreSQL + pgvector backend for Holix agent memory / skills search."""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from core.memory.vector_protocol import empty_query_result

logger = logging.getLogger(__name__)

Embedder = Callable[[list[str]], list[list[float]]]
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str, default: str) -> str:
    raw = (name or "").strip()
    if _IDENT_RE.match(raw):
        return raw
    return default


def _vec_literal(values: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in values) + "]"


def _pad(vec: list[float], dim: int) -> list[float]:
    if len(vec) == dim:
        return [float(x) for x in vec]
    if len(vec) > dim:
        return [float(x) for x in vec[:dim]]
    return [float(x) for x in vec] + [0.0] * (dim - len(vec))


def _as_meta(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


class PgVectorCollection:
    def __init__(self, backend: PgVectorBackend, name: str) -> None:
        self._backend = backend
        self._name = name

    def add(
        self,
        documents: list[str],
        ids: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        self.upsert(documents, ids, metadatas)

    def upsert(
        self,
        documents: list[str],
        ids: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        self._backend.upsert(self._name, documents, ids, metadatas)

    def query(
        self,
        query_texts: list[str],
        n_results: int = 8,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._backend.query(self._name, query_texts, n_results, where)

    def delete(
        self,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> None:
        self._backend.delete(self._name, ids=ids, where=where)

    def count(self) -> int:
        return self._backend.count(self._name)


class PgVectorBackend:
    chroma_client = None

    def __init__(
        self,
        *,
        dsn: str,
        profile: str,
        dim: int,
        table: str,
        embedder: Embedder,
    ) -> None:
        self._dsn = dsn
        self._profile = profile or "default"
        self._dim = max(int(dim), 1)
        self._table = _safe_ident(table, "holix_vectors")
        self._embedder = embedder
        self._lock = threading.RLock()
        self._ready = False
        self._pool: Any = None
        try:
            from psycopg_pool import ConnectionPool

            self._pool = ConnectionPool(
                conninfo=self._dsn,
                min_size=1,
                max_size=8,
                open=True,
                kwargs={"autocommit": True},
            )
        except Exception:
            self._pool = None

    @contextmanager
    def _connect(self):
        if self._pool is not None:
            with self._pool.connection() as conn:
                yield conn
            return
        import psycopg

        with psycopg.connect(self._dsn, autocommit=True) as conn:
            yield conn

    def _ensure_schema(self) -> None:
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            table = self._table
            dim = self._dim
            with self._connect() as conn:
                conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                      profile TEXT NOT NULL,
                      collection TEXT NOT NULL,
                      id TEXT NOT NULL,
                      document TEXT NOT NULL,
                      metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                      embedding vector({dim}) NOT NULL,
                      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                      PRIMARY KEY (profile, collection, id)
                    )
                    """
                )
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS {table}_coll_idx ON {table} (profile, collection)"
                )
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS {table}_meta_idx ON {table} USING gin (metadata)"
                )
                try:
                    conn.execute(
                        f"CREATE INDEX IF NOT EXISTS {table}_hnsw_idx "
                        f"ON {table} USING hnsw (embedding vector_cosine_ops)"
                    )
                except Exception as exc:
                    logger.info("pgvector HNSW index skipped: %s", exc)
            self._ready = True

    def get_collection(self, name: str) -> PgVectorCollection:
        self._ensure_schema()
        return PgVectorCollection(self, str(name or "memory"))

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        raw = self._embedder(texts)
        return [_pad(list(row), self._dim) for row in raw]

    def upsert(
        self,
        collection: str,
        documents: list[str],
        ids: list[str],
        metadatas: list[dict[str, Any]] | None,
    ) -> None:
        if not documents or not ids:
            return
        self._ensure_schema()
        vectors = self._embed(list(documents))
        sql = (
            f"INSERT INTO {self._table} "
            f"(profile, collection, id, document, metadata, embedding) "
            f"VALUES (%s, %s, %s, %s, %s::jsonb, %s::vector) "
            f"ON CONFLICT (profile, collection, id) DO UPDATE SET "
            f"document = EXCLUDED.document, metadata = EXCLUDED.metadata, "
            f"embedding = EXCLUDED.embedding, updated_at = now()"
        )
        with self._connect() as conn:
            for i, doc_id in enumerate(ids):
                meta = metadatas[i] if metadatas and i < len(metadatas) else {}
                vec = vectors[i] if i < len(vectors) else [0.0] * self._dim
                conn.execute(
                    sql,
                    (
                        self._profile,
                        collection,
                        str(doc_id),
                        documents[i],
                        json.dumps(meta or {}, ensure_ascii=False),
                        _vec_literal(vec),
                    ),
                )

    def query(
        self,
        collection: str,
        query_texts: list[str],
        n_results: int,
        where: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not query_texts or n_results <= 0:
            return empty_query_result()
        self._ensure_schema()
        qvec = self._embed([query_texts[0]])[0]
        literal = _vec_literal(qvec)
        where_sql = ""
        simple: dict[str, Any] = {}
        if where:
            simple = {str(k): v for k, v in where.items() if not str(k).startswith("$")}
            if simple:
                where_sql = " AND v.metadata @> %s::jsonb"
        sql = (
            f"WITH q AS (SELECT %s::vector AS v) "
            f"SELECT v.id, v.document, v.metadata, (v.embedding <=> q.v) AS distance "
            f"FROM {self._table} v, q "
            f"WHERE v.profile = %s AND v.collection = %s{where_sql} "
            f"ORDER BY v.embedding <=> q.v "
            f"LIMIT %s"
        )
        bind: list[Any] = [literal, self._profile, collection]
        if where_sql:
            bind.append(json.dumps(simple, ensure_ascii=False))
        bind.append(max(int(n_results), 1))
        try:
            with self._connect() as conn:
                rows = conn.execute(sql, bind).fetchall()
        except Exception as exc:
            logger.warning("pgvector query failed: %s", exc)
            return empty_query_result()
        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict[str, Any]] = []
        dists: list[float] = []
        for row in rows:
            ids.append(str(row[0]))
            docs.append(str(row[1] or ""))
            metas.append(_as_meta(row[2]))
            dists.append(float(row[3] or 0.0))
        return {
            "ids": [ids],
            "documents": [docs],
            "metadatas": [metas],
            "distances": [dists],
        }

    def delete(
        self,
        collection: str,
        *,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> None:
        self._ensure_schema()
        if ids:
            with self._connect() as conn:
                conn.execute(
                    f"DELETE FROM {self._table} "
                    f"WHERE profile = %s AND collection = %s AND id = ANY(%s)",
                    (self._profile, collection, list(ids)),
                )
            return
        if where:
            simple = {str(k): v for k, v in where.items() if not str(k).startswith("$")}
            if not simple:
                return
            with self._connect() as conn:
                conn.execute(
                    f"DELETE FROM {self._table} "
                    f"WHERE profile = %s AND collection = %s AND metadata @> %s::jsonb",
                    (self._profile, collection, json.dumps(simple, ensure_ascii=False)),
                )

    def count(self, collection: str) -> int:
        self._ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) FROM {self._table} WHERE profile = %s AND collection = %s",
                (self._profile, collection),
            ).fetchone()
        return int(row[0] or 0) if row else 0
