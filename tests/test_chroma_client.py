"""Process-wide Chroma PersistentClient singleton."""

from __future__ import annotations

from pathlib import Path

from core.di.runtime_config import HolixRuntimeConfig
from core.memory.chroma_client import (
    chroma_client_key,
    get_persistent_client,
    reset_persistent_clients,
)
from core.memory.facade import MemoryFacade


class _FakeClient:
    def __init__(self, path=None, settings=None, **_kwargs):
        self.path = path
        self.settings = settings

    def get_collection(self, name, embedding_function=None, **_kwargs):
        return {"name": name, "embedding_function": embedding_function}

    def create_collection(self, **_kwargs):
        raise AssertionError("must reuse existing collection")


def test_get_persistent_client_reuses_same_path(tmp_path, monkeypatch) -> None:
    created: list[str] = []

    def _factory(*, path, settings=None, **kwargs):
        created.append(path)
        return _FakeClient(path=path, settings=settings)

    monkeypatch.setattr("chromadb.PersistentClient", _factory)
    reset_persistent_clients()
    a = get_persistent_client(tmp_path / "vec")
    b = get_persistent_client(tmp_path / "vec")
    c = get_persistent_client(tmp_path / "other")
    assert a is b
    assert a is not c
    assert created == [
        chroma_client_key(tmp_path / "vec"),
        chroma_client_key(tmp_path / "other"),
    ]
    reset_persistent_clients()


def test_memory_facade_shares_vector_client(tmp_path, monkeypatch) -> None:
    created: list[str] = []

    def _factory(*, path, settings=None, **kwargs):
        created.append(path)
        return _FakeClient(path=path, settings=settings)

    monkeypatch.setattr("chromadb.PersistentClient", _factory)
    reset_persistent_clients()
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        memory_db_path=str(tmp_path / "mem.db"),
        vector_db_path=str(tmp_path / "vector_db"),
        ltm_db_path=str(tmp_path / "ltm.db"),
        memory_chroma_collection="test_memory",
        enable_long_term_memory=True,
    )
    facade = MemoryFacade(cfg)
    assert facade.conversations.chroma_client is facade._ltm._vector_store._chroma_client
    vec_key = chroma_client_key(tmp_path / "vector_db")
    assert created.count(vec_key) == 1
    reset_persistent_clients()


def test_second_facade_reuses_client(tmp_path, monkeypatch) -> None:
    created: list[str] = []

    def _factory(*, path, settings=None, **kwargs):
        created.append(path)
        return _FakeClient(path=path, settings=settings)

    monkeypatch.setattr("chromadb.PersistentClient", _factory)
    reset_persistent_clients()
    cfg = HolixRuntimeConfig.from_settings().with_overrides(
        memory_db_path=str(tmp_path / "mem.db"),
        vector_db_path=str(tmp_path / "vector_db"),
        ltm_db_path=str(tmp_path / "ltm.db"),
        memory_chroma_collection="test_memory",
        enable_long_term_memory=True,
    )
    first = MemoryFacade(cfg)
    second = MemoryFacade(cfg)
    assert first.conversations.chroma_client is second.conversations.chroma_client
    vec_key = chroma_client_key(Path(tmp_path / "vector_db"))
    assert created.count(vec_key) == 1
    reset_persistent_clients()
