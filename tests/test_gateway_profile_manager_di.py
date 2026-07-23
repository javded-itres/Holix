"""ProfileManager is provided by Dishka for /api/holix management routes."""

from __future__ import annotations

import pytest
from api.services.holix_deps import ensure_profile_exists, load_existing_profile
from core.di.container import create_async_container, resolve_gateway_runtime_config
from core.profile.service import ProfileManager
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_gateway_container_provides_profile_manager():
    container = create_async_container(resolve_gateway_runtime_config(), gateway=True)
    try:
        manager = await container.get(ProfileManager)
        assert isinstance(manager, ProfileManager)
        # APP scope: same instance
        again = await container.get(ProfileManager)
        assert again is manager
    finally:
        await container.close()


def test_ensure_profile_exists_404(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    manager = ProfileManager()
    with pytest.raises(HTTPException) as exc:
        ensure_profile_exists(manager, "missing-profile-xyz")
    assert exc.value.status_code == 404


def test_load_existing_profile_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    manager = ProfileManager()
    manager.create_profile("di-test", with_access_key=False, inherit_global=False)
    m, config = load_existing_profile(manager, "di-test")
    assert m is manager
    assert config is not None
