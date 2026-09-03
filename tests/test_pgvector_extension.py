"""ensure_pgvector_extension: deploy may create the extension as superuser."""

from __future__ import annotations

import pytest
from core.memory.pgvector_store import ensure_pgvector_extension


class _Result:
    def __init__(self, row: object) -> None:
        self._row = row

    def fetchone(self) -> object:
        return self._row


class _Conn:
    def __init__(self, *, create_exc: Exception | None = None, ext_row: object = None) -> None:
        self.create_exc = create_exc
        self.ext_row = ext_row
        self.sql: list[str] = []

    def execute(self, sql: str, *args: object) -> _Result:
        self.sql.append(sql)
        if sql.strip().upper().startswith("CREATE EXTENSION"):
            if self.create_exc is not None:
                raise self.create_exc
            return _Result(None)
        if "pg_extension" in sql:
            return _Result(self.ext_row)
        return _Result(None)


def test_ensure_extension_creates_when_allowed() -> None:
    conn = _Conn()
    ensure_pgvector_extension(conn)
    assert any("CREATE EXTENSION" in s for s in conn.sql)


def test_ensure_extension_accepts_preinstalled() -> None:
    conn = _Conn(create_exc=RuntimeError("must be superuser"), ext_row=(1,))
    ensure_pgvector_extension(conn)
    assert any("pg_extension" in s for s in conn.sql)


def test_ensure_extension_missing_raises() -> None:
    conn = _Conn(create_exc=RuntimeError("must be superuser"), ext_row=None)
    with pytest.raises(RuntimeError, match="superuser"):
        ensure_pgvector_extension(conn)
