"""ProfileAgentRegistry crypto unlock integration tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cli.core import ProfileManager
from core.crypto.bootstrap import enable_profile_encryption
from core.crypto.encrypted_fs import is_encrypted_file
from core.crypto.gateway_crypto import GatewayProfileLockedError
from core.crypto.unlock_context import clear_profile_session_unlock, get_profile_session_dek
from core.gateway.profile_registry import ProfileAgentRegistry


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _seed_memory(profile_dir: Path) -> None:
    memory_db = profile_dir / "data" / "memory" / "memory.db"
    memory_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(memory_db))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('dialog-secret')")
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_registry_unlocks_non_host_profile(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    monkeypatch.setenv("HOLIX_UNLOCK_KEY", "unlock-key-lain-42")
    manager = ProfileManager()
    manager.create_profile("lain", inherit_global=False)
    _seed_memory(manager.get_profile_dir("lain"))
    enable_profile_encryption(manager, "lain", "unlock-key-lain-42")

    registry = ProfileAgentRegistry("default")
    mock_agent = MagicMock()
    mock_agent._initialized = True
    mock_container = AsyncMock()
    mock_container.close = AsyncMock()

    with patch(
        "core.di.container.create_agent",
        new_callable=AsyncMock,
    ) as create_agent:
        create_agent.return_value = (mock_agent, mock_container)
        agent = await registry.get_agent("lain")
        assert agent is mock_agent
        assert get_profile_session_dek("lain") is not None


@pytest.mark.asyncio
async def test_registry_locked_without_unlock_key(holix_home, monkeypatch) -> None:
    monkeypatch.delenv("HOLIX_UNLOCK_KEY", raising=False)
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    manager = ProfileManager()
    manager.create_profile("mashadulya", inherit_global=False)
    enable_profile_encryption(manager, "mashadulya", "unlock-key-masha-77", encrypt_existing=False)
    clear_profile_session_unlock("mashadulya")

    registry = ProfileAgentRegistry("default")
    with pytest.raises(GatewayProfileLockedError):
        await registry.get_agent("mashadulya")


@pytest.mark.asyncio
async def test_registry_dispose_seals_memory(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(holix_home))
    monkeypatch.setenv("HOLIX_UNLOCK_KEY", "unlock-key-docs-11")
    manager = ProfileManager()
    manager.create_profile("docs", inherit_global=False)
    pdir = manager.get_profile_dir("docs")
    _seed_memory(pdir)
    enable_profile_encryption(manager, "docs", "unlock-key-docs-11")
    memory_db = pdir / "data" / "memory" / "memory.db"

    registry = ProfileAgentRegistry("default")
    mock_agent = MagicMock()
    mock_agent._initialized = True
    mock_container = AsyncMock()
    mock_container.close = AsyncMock()

    with patch(
        "core.di.container.create_agent",
        new_callable=AsyncMock,
    ) as create_agent:
        create_agent.return_value = (mock_agent, mock_container)
        await registry.get_agent("docs")
        await registry.shutdown()

    assert get_profile_session_dek("docs") is None
    assert is_encrypted_file(memory_db)