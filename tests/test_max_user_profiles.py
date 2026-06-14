"""Tests for MAX user id → Holix profile bindings."""

from __future__ import annotations

import json

import pytest
from integrations.max.user_profiles import (
    ENV_KEY,
    format_user_profiles_text,
    load_user_profiles,
    max_users_path,
    parse_user_profiles_text,
    remove_user_profile,
    resolve_user_profile,
    save_user_profiles,
    set_user_profile,
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


def test_save_and_load_user_profiles(holix_home) -> None:
    from integrations.max.env_store import save_max_env

    save_max_env({"MAX_ACCESS_TOKEN": "a" * 20}, profile="shared")
    path = save_user_profiles("shared", {111: "alice", 222: "bob"})
    assert path == max_users_path("shared")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"111": "alice", "222": "bob"}
    assert load_user_profiles("shared") == {111: "alice", 222: "bob"}
    assert resolve_user_profile("shared", 111) == "alice"


def test_remove_user_profile(holix_home) -> None:
    from integrations.max.env_store import save_max_env

    save_max_env({"MAX_ACCESS_TOKEN": "a" * 20}, profile="bot")
    set_user_profile("bot", 1, "alice")
    path = remove_user_profile("bot", 1)
    assert path is not None
    assert load_user_profiles("bot") == {}


def test_validate_user_profiles_text() -> None:
    assert validate_user_profiles_text("123:alice") is None
    assert validate_user_profiles_text("bad") is not None
    assert ENV_KEY == "HOLIX_MAX_USER_PROFILES"