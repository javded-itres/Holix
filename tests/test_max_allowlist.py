"""MAX user allowlist — default-deny behavior."""

from __future__ import annotations

import pytest
from integrations.max.bot import HelixMaxBot
from integrations.max.config import MaxSettings


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


def test_default_deny_without_allowlist() -> None:
    settings = MaxSettings(access_token="a" * 20)
    assert not settings.is_user_allowed(42)


def test_allowlist_permits_only_listed_users() -> None:
    settings = MaxSettings(access_token="a" * 20, allowed_user_ids="42, 99")
    assert settings.is_user_allowed(42)
    assert settings.is_user_allowed(99)
    assert not settings.is_user_allowed(1)


def test_can_start_with_access_requests() -> None:
    settings = MaxSettings(access_token="a" * 20, access_requests=True)
    assert settings.can_start_without_allowlist()


def test_bot_allowed_delegates_to_settings(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.max.env_store import save_max_env

    save_max_env(
        {"MAX_ACCESS_TOKEN": "a" * 20, "HOLIX_MAX_ALLOWED_USERS": "7"},
        profile="default",
    )
    bot = HelixMaxBot(MaxSettings(access_token="a" * 20, allowed_user_ids="7"))
    assert bot._allowed(7)
    assert not bot._allowed(8)