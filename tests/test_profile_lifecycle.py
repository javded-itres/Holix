"""Tests for profile deletion with Telegram notification."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from cli.core import ProfileManager
from core.profile.lifecycle import (
    delete_profile_with_notification,
    find_telegram_users_for_profile,
    remove_profile_telegram_bindings,
)
from integrations.telegram.user_profiles import (
    TELEGRAM_USERS_FILE,
    load_user_profiles,
    set_user_profile,
)


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_find_telegram_users_for_profile(holix_home) -> None:
    manager = ProfileManager()
    manager.create_profile("bot", inherit_global=False)
    manager.create_profile("alice", inherit_global=False)
    manager.create_profile("bob", inherit_global=False)

    users_path = manager.get_profile_dir("bot") / TELEGRAM_USERS_FILE
    users_path.write_text(
        json.dumps({"111": "alice", "222": "bob", "333": "alice"}),
        encoding="utf-8",
    )

    hits = find_telegram_users_for_profile("alice")
    assert sorted(hits) == [("bot", 111), ("bot", 333)]


def test_load_user_profiles_falls_back_to_default(holix_home) -> None:
    manager = ProfileManager()
    manager.create_profile("default", inherit_global=False)
    manager.create_profile("docs", inherit_global=False)
    default_users = manager.get_profile_dir("default") / TELEGRAM_USERS_FILE
    default_users.write_text(json.dumps({"42": "carol"}), encoding="utf-8")

    mapping = load_user_profiles("docs")
    assert mapping == {42: "carol"}


def test_delete_profile_notifies_and_removes_mapping(holix_home, monkeypatch) -> None:
    manager = ProfileManager()
    manager.create_profile("bot", inherit_global=False)
    manager.create_profile("carol", inherit_global=False)
    set_user_profile("bot", 555, "carol")

    notified: list[int] = []

    def _fake_notify(bot_profile: str, user_id: int, *, deleted_profile: str) -> None:
        assert bot_profile == "bot"
        assert deleted_profile == "carol"
        notified.append(user_id)

    with patch(
        "core.profile.lifecycle.notify_profile_deletion_sync",
        side_effect=_fake_notify,
    ):
        result = delete_profile_with_notification("carol", notify=True, manager=manager)

    assert result.deleted is True
    assert result.notified == [555]
    assert result.mappings_removed == 1
    assert not manager.profile_exists("carol")
    assert load_user_profiles("bot") == {}


def test_remove_profile_telegram_bindings(holix_home) -> None:
    manager = ProfileManager()
    manager.create_profile("bot", inherit_global=False)
    set_user_profile("bot", 1, "dave")
    set_user_profile("bot", 2, "erin")

    count = remove_profile_telegram_bindings("dave")
    assert count == 1
    assert load_user_profiles("bot") == {2: "erin"}