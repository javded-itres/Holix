"""Cross-profile access: users must not see or manage other users' profiles."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cli.core import ProfileManager
from core.security.workspace_command_guard import validate_workspace_command
from core.tools.execution_context import profile_scope, reset_profile_scope
from core.tools.terminal import TerminalTool
from fastapi.testclient import TestClient


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def non_admin_client(holix_home: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import asyncio

    import api.deps
    import api.gateway
    import api.state
    from fastapi.testclient import TestClient

    mock_registry = MagicMock()
    mock_registry.list_loaded_profiles = MagicMock(return_value=[])

    async def _non_admin_key():
        return {"permissions": ["read", "write", "execute"], "rate_limit": 1000}

    async def _fake_registry():
        return mock_registry

    monkeypatch.setattr(api.state, "registry", mock_registry)
    monkeypatch.setattr(api.state, "host_profile", "default")
    monkeypatch.setattr(api.state, "_agent_request_lock", asyncio.Lock())

    api.gateway.app.dependency_overrides[api.deps.verify_api_key] = _non_admin_key
    api.gateway.app.dependency_overrides[api.deps.get_registry] = _fake_registry

    client = TestClient(api.gateway.app)
    yield client
    api.gateway.app.dependency_overrides.clear()


def _alice_headers(alice_key: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer test-key",
        "X-Holix-Profile": "alice",
        "X-Holix-Profile-Key": alice_key,
    }


def _bob_headers(bob_key: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer test-key",
        "X-Holix-Profile": "bob",
        "X-Holix-Profile-Key": bob_key,
    }


def test_non_admin_cannot_list_all_profiles(
    holix_home: Path,
    non_admin_client: TestClient,
) -> None:
    manager = ProfileManager()
    manager.create_profile("alice", with_access_key=True)
    alice_key = manager.pop_last_created_access_key()
    manager.create_profile("bob", with_access_key=True)
    bob_key = manager.pop_last_created_access_key()
    assert alice_key and bob_key

    response = non_admin_client.get("/api/holix/profiles", headers=_alice_headers(alice_key))
    assert response.status_code == 403


def test_bob_cannot_read_alice_protected_profile(
    holix_home: Path,
    non_admin_client: TestClient,
) -> None:
    manager = ProfileManager()
    manager.create_profile("alice", with_access_key=True)
    alice_key = manager.pop_last_created_access_key()
    manager.create_profile("bob", with_access_key=True)
    bob_key = manager.pop_last_created_access_key()
    assert alice_key and bob_key

    denied = non_admin_client.get(
        "/api/holix/profiles/alice",
        headers=_bob_headers(bob_key),
    )
    assert denied.status_code == 403

    allowed = non_admin_client.get(
        "/api/holix/profiles/alice",
        headers=_alice_headers(alice_key),
    )
    assert allowed.status_code == 200
    assert allowed.json()["profile"] == "alice"


def test_bob_cannot_use_alice_key_to_access_alice_profile(
    holix_home: Path,
    non_admin_client: TestClient,
) -> None:
    manager = ProfileManager()
    manager.create_profile("alice", with_access_key=True)
    alice_key = manager.pop_last_created_access_key()
    manager.create_profile("bob", with_access_key=True)
    bob_key = manager.pop_last_created_access_key()
    assert alice_key and bob_key

    denied = non_admin_client.get(
        "/api/holix/profiles/alice",
        headers={
            "Authorization": "Bearer test-key",
            "X-Holix-Profile": "bob",
            "X-Holix-Profile-Key": alice_key,
        },
    )
    assert denied.status_code == 403

    wrong_key = non_admin_client.get(
        "/api/holix/profiles/alice",
        headers={
            "Authorization": "Bearer test-key",
            "X-Holix-Profile": "alice",
            "X-Holix-Profile-Key": bob_key,
        },
    )
    assert wrong_key.status_code == 403


def test_owner_can_read_own_profile_status(
    holix_home: Path,
    non_admin_client: TestClient,
) -> None:
    manager = ProfileManager()
    manager.create_profile("alice", with_access_key=True)
    alice_key = manager.pop_last_created_access_key()

    response = non_admin_client.get(
        "/api/holix/profiles/alice/status",
        headers=_alice_headers(alice_key),
    )
    assert response.status_code == 200
    assert response.json()["profile"] == "alice"


@pytest.mark.asyncio
async def test_terminal_blocks_other_profile_paths(holix_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from config import settings

    manager = ProfileManager()
    manager.create_profile("alice")
    manager.create_profile("bob")
    alice_cfg = manager.load_profile("alice")

    monkeypatch.setattr(settings, "enable_terminal_tool", True)
    monkeypatch.setattr(settings, "terminal_command_whitelist", False)
    from core.tools import terminal as terminal_mod

    monkeypatch.setattr(terminal_mod.settings, "terminal_command_whitelist", False)
    from core.tools.execution_context import reset_workspace_scope, workspace_scope

    ws_tokens = workspace_scope(
        workspace_root=alice_cfg.workspace_root,
        workspace_jail_enabled=True,
    )
    prof_token = profile_scope("alice")
    try:
        tool = TerminalTool()
        out = await tool.execute("cat ~/.holix/profiles/bob/config.yaml")
        assert "blocked" in out.lower() or "not allowed" in out.lower()
    finally:
        reset_profile_scope(prof_token)
        reset_workspace_scope(ws_tokens)


def test_workspace_guard_blocks_holix_profile_paths() -> None:
    allowed, err = validate_workspace_command(
        "ls ~/.holix/profiles/bob",
        "/tmp/alice/workspace",
    )
    assert not allowed
    assert "holix" in err.lower() or "profile" in err.lower()