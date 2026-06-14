"""Shared messenger layer — telegram wrappers stay compatible."""

from __future__ import annotations

import pytest
from integrations.telegram.allowlist import add_allowed_user, load_allowed_user_ids
from integrations.telegram.env_store import read_telegram_env_values, save_telegram_env


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


def test_telegram_env_via_messenger(holix_home) -> None:
    save_telegram_env(
        {"TELEGRAM_BOT_TOKEN": "123:" + "x" * 30, "HOLIX_TELEGRAM_ALLOWED_USERS": "9"},
        profile="default",
    )
    values = read_telegram_env_values("default")
    assert values["HOLIX_TELEGRAM_ALLOWED_USERS"] == "9"
    assert load_allowed_user_ids("default") == {9}
    add_allowed_user("default", 10)
    assert load_allowed_user_ids("default") == {9, 10}