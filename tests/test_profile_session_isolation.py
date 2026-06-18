"""Cross-profile session isolation: memory DB, tools, and gateway API."""

from __future__ import annotations

import uuid

import pytest
from cli.core import ProfileManager, resolve_profile_storage_paths
from core.di.runtime_config import HolixRuntimeConfig
from core.memory.facade import MemoryFacade
from core.tools.execution_context import (
    memory_facade_scope,
    profile_scope,
    reset_memory_facade_scope,
    reset_profile_scope,
)
from core.tools.session_memory import ReadSessionTool, SearchSessionsTool
from fastapi.testclient import TestClient


def _profile_headers(profile: str, base: dict[str, str]) -> dict[str, str]:
    return {**base, "X-Holix-Profile": profile}


@pytest.fixture
def holix_home(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


async def _memory_for_profile(profile_name: str) -> MemoryFacade:
    manager = ProfileManager()
    if not manager.profile_exists(profile_name):
        manager.create_profile(profile_name)
    profile_dir = manager.get_profile_dir(profile_name)
    cfg = resolve_profile_storage_paths(
        profile_name,
        manager.load_profile(profile_name),
        profile_dir=profile_dir,
    )
    runtime = HolixRuntimeConfig.from_profile(cfg).with_overrides(
        memory_chroma_collection=f"iso_{profile_name}_{uuid.uuid4().hex[:8]}",
        enable_long_term_memory=False,
    )
    facade = MemoryFacade(runtime)
    await facade.initialize_db()
    return facade


def test_profiles_use_distinct_memory_databases(holix_home) -> None:
    manager = ProfileManager()
    manager.create_profile("alice")
    manager.create_profile("bob")

    alice_cfg = resolve_profile_storage_paths(
        "alice",
        manager.load_profile("alice"),
        profile_dir=manager.get_profile_dir("alice"),
    )
    bob_cfg = resolve_profile_storage_paths(
        "bob",
        manager.load_profile("bob"),
        profile_dir=manager.get_profile_dir("bob"),
    )

    assert alice_cfg.memory_db_path != bob_cfg.memory_db_path
    assert "/profiles/alice/" in alice_cfg.memory_db_path.replace("\\", "/")
    assert "/profiles/bob/" in bob_cfg.memory_db_path.replace("\\", "/")


@pytest.mark.asyncio
async def test_bob_cannot_search_alice_sessions(holix_home) -> None:
    alice_mem = await _memory_for_profile("alice")
    bob_mem = await _memory_for_profile("bob")

    await alice_mem.save_message(
        "alice-private-sess",
        "user",
        "alice-secret-token: ZEBRA-42 only for alice",
    )
    await bob_mem.save_message(
        "bob-private-sess",
        "user",
        "bob-public-topic: weather in paris",
    )

    tool = SearchSessionsTool()
    bob_token = memory_facade_scope(bob_mem)
    prof_token = profile_scope("bob")
    try:
        out = await tool.execute(query="ZEBRA-42 alice-secret", top_k=10)
    finally:
        reset_memory_facade_scope(bob_token)
        reset_profile_scope(prof_token)

    assert "ZEBRA-42" not in out
    assert "alice-private-sess" not in out
    if "bob-private-sess" in out:
        assert "alice-secret" not in out.lower()


@pytest.mark.asyncio
async def test_bob_cannot_read_alice_session_by_id(holix_home) -> None:
    alice_mem = await _memory_for_profile("alice")
    bob_mem = await _memory_for_profile("bob")

    await alice_mem.save_message(
        "alice-private-sess",
        "user",
        "classified payload ALPHA-999",
    )

    tool = ReadSessionTool()
    bob_token = memory_facade_scope(bob_mem)
    prof_token = profile_scope("bob")
    try:
        out = await tool.execute(conversation_id="alice-private-sess", limit=20)
    finally:
        reset_memory_facade_scope(bob_token)
        reset_profile_scope(prof_token)

    assert "ALPHA-999" not in out
    assert "no messages" in out.lower() or "does not exist" in out.lower()


@pytest.mark.asyncio
async def test_bob_list_conversations_excludes_alice(holix_home) -> None:
    alice_mem = await _memory_for_profile("alice")
    bob_mem = await _memory_for_profile("bob")

    await alice_mem.save_message("alice-only", "user", "hello alice")
    await bob_mem.save_message("bob-only", "user", "hello bob")

    alice_list = await alice_mem.list_recent_conversations(limit=20)
    bob_list = await bob_mem.list_recent_conversations(limit=20)

    alice_ids = {row["conversation_id"] for row in alice_list}
    bob_ids = {row["conversation_id"] for row in bob_list}

    assert "alice-only" in alice_ids
    assert "alice-only" not in bob_ids
    assert "bob-only" in bob_ids
    assert "bob-only" not in alice_ids


@pytest.mark.asyncio
async def test_session_tools_fallback_uses_profile_scoped_memory(holix_home) -> None:
    """Without memory_facade_scope, tools resolve DB via profile_scope."""
    alice_mem = await _memory_for_profile("alice")
    bob_mem = await _memory_for_profile("bob")

    await alice_mem.save_message("fallback-alice", "user", "fallback-secret DELTA-77")
    await bob_mem.save_message("fallback-bob", "user", "bob unrelated chatter")

    tool = ReadSessionTool()
    prof_token = profile_scope("bob")
    try:
        out = await tool.execute(conversation_id="fallback-alice", limit=10)
    finally:
        reset_profile_scope(prof_token)

    assert "DELTA-77" not in out
    assert "no messages" in out.lower() or "does not exist" in out.lower()


def test_gateway_session_list_isolated(
    gateway_client: TestClient,
    gateway_auth_headers: dict[str, str],
) -> None:
    created = gateway_client.post(
        "/api/sessions",
        headers=_profile_headers("alice", gateway_auth_headers),
        json={"title": "alice-only session"},
    )
    assert created.status_code == 200
    alice_sid = created.json()["id"]

    bob_list = gateway_client.get(
        "/api/sessions",
        headers=_profile_headers("bob", gateway_auth_headers),
    )
    assert bob_list.status_code == 200
    bob_ids = {s["id"] for s in bob_list.json()["sessions"]}
    assert alice_sid not in bob_ids

    alice_list = gateway_client.get(
        "/api/sessions",
        headers=_profile_headers("alice", gateway_auth_headers),
    )
    alice_ids = {s["id"] for s in alice_list.json()["sessions"]}
    assert alice_sid in alice_ids