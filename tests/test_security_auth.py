import pytest

from config import settings
from core.security.auth import APIKeyManager


@pytest.mark.asyncio
async def test_api_key_roundtrip(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    updated = settings.model_copy(update={"api_key_pepper": "test-pepper"})
    monkeypatch.setattr("config.settings", updated)
    monkeypatch.setattr("core.security.auth.settings", updated)

    mgr = APIKeyManager(str(tmp_path / "keys.db"))
    await mgr.initialize_db()
    raw = await mgr.create_api_key("ci", permissions="admin", rate_limit=10)
    info = await mgr.validate_api_key(raw)
    assert info is not None
    assert "admin" in info["permissions"]


def test_hash_key_requires_pepper(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    updated = settings.model_copy(update={"api_key_pepper": ""})
    monkeypatch.setattr("config.settings", updated)
    monkeypatch.setattr("core.security.auth.settings", updated)

    mgr = APIKeyManager(str(tmp_path / "keys.db"))
    with pytest.raises(RuntimeError, match="HELIX_API_KEY_PEPPER"):
        mgr.hash_key("hx_test")