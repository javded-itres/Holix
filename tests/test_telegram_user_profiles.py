"""Tests for Telegram user id → Holix profile bindings."""

from __future__ import annotations

import json

import pytest
from integrations.telegram.user_profiles import (
    ENV_KEY,
    format_user_profiles_text,
    load_user_profiles,
    parse_user_profiles_text,
    remove_user_profile,
    resolve_user_profile,
    save_user_profiles,
    set_user_profile,
    telegram_users_path,
    validate_user_profiles_text,
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


def test_parse_and_format_user_profiles() -> None:
    mapping = parse_user_profiles_text(" 123:alice, 456:bob ")
    assert mapping == {123: "alice", 456: "bob"}
    assert format_user_profiles_text(mapping) == "123:alice,456:bob"


def test_validate_user_profiles_text() -> None:
    assert validate_user_profiles_text("123:alice,456:bob") is None
    assert validate_user_profiles_text("bad") is not None


def test_save_and_load_user_profiles(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="shared")
    path = save_user_profiles("shared", {111: "alice", 222: "bob"})
    assert path == telegram_users_path("shared")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"111": "alice", "222": "bob"}
    assert load_user_profiles("shared") == {111: "alice", 222: "bob"}
    assert resolve_user_profile("shared", 111) == "alice"
    assert resolve_user_profile("shared", 999) is None


def test_env_user_profiles_merged(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env(
        {
            "TELEGRAM_BOT_TOKEN": "1:abc",
            ENV_KEY: "333:carol",
        },
        profile="shared",
    )
    path = telegram_users_path("shared")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"111": "alice"}\n', encoding="utf-8")
    assert load_user_profiles("shared") == {111: "alice", 333: "carol"}


def test_set_and_remove_user_profile(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.telegram.env_store import save_telegram_env

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="shared")
    set_user_profile("shared", 42, "work")
    assert resolve_user_profile("shared", 42) == "work"
    remove_user_profile("shared", 42)
    assert resolve_user_profile("shared", 42) is None