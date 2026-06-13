"""MAX administrator env persistence."""

from __future__ import annotations

import pytest
from integrations.max.admin import (
    clear_admin_user,
    is_max_admin,
    load_admin_holix_profile,
    load_admin_user_id,
    set_admin_user,
)


@pytest.fixture
def holix_home(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import cli.core as cli_core

    root = tmp_path / "holix"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("HOLIX_HOME", str(root))
    monkeypatch.setattr(cli_core, "HOLIX_HOME", root)
    monkeypatch.setattr(cli_core, "PROFILES_DIR", profiles)
    return root


def test_admin_roundtrip(holix_home) -> None:
    from integrations.max.env_store import save_max_env

    save_max_env({"MAX_ACCESS_TOKEN": "a" * 20}, profile="bot")
    assert load_admin_user_id("bot") is None
    set_admin_user("bot", 42, holix_profile="admin")
    assert load_admin_user_id("bot") == 42
    assert load_admin_holix_profile("bot") == "admin"
    assert is_max_admin("bot", 42)
    assert not is_max_admin("bot", 1)
    assert clear_admin_user("bot")
    assert load_admin_user_id("bot") is None