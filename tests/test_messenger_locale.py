"""Messenger (Telegram/MAX) default locale tests."""

from __future__ import annotations

from pathlib import Path

import cli.core as cli_core
import pytest
from core.i18n import LocaleStore
from integrations.messenger.locale import (
    MESSENGER_DEFAULT_LOCALE,
    apply_messenger_locale,
    bootstrap_messenger_locales,
    ensure_messenger_locale,
    messenger_host_locale,
    messenger_locale,
)
from integrations.messenger.platforms import TELEGRAM_PLATFORM


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "holix"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("HOLIX_HOME", str(root))
    monkeypatch.setattr(cli_core, "HOLIX_HOME", root)
    monkeypatch.setattr(cli_core, "PROFILES_DIR", profiles)
    cli_core._unlocked_profiles.clear()
    yield root
    cli_core._unlocked_profiles.clear()


class _FakeHost:
    def __init__(self, profile: str = "tg_user") -> None:
        self.profile = profile


def test_messenger_default_locale_is_ru() -> None:
    assert MESSENGER_DEFAULT_LOCALE == "ru"


def test_messenger_locale_without_file_defaults_to_ru(
    holix_home: Path,
) -> None:
    assert messenger_locale("fresh_user") == "ru"


def test_ensure_messenger_locale_persists_ru(holix_home: Path) -> None:
    assert ensure_messenger_locale("fresh_user") == "ru"
    assert LocaleStore("fresh_user").get() == "ru"


def test_apply_messenger_locale_overwrites_existing(holix_home: Path) -> None:
    LocaleStore("worker").set("en")
    assert apply_messenger_locale("worker") == "ru"
    assert LocaleStore("worker").get() == "ru"


def test_messenger_host_locale_uses_profile(holix_home: Path) -> None:
    apply_messenger_locale("host_profile")
    assert messenger_host_locale(_FakeHost("host_profile")) == "ru"


def test_bootstrap_messenger_locales_for_bot_and_users(
    holix_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cli.core import ProfileManager
    from integrations.telegram.env_store import save_telegram_env

    manager = ProfileManager()
    manager.create_profile("shared", inherit_global=True)
    manager.create_profile("alice", inherit_global=True)

    from integrations.telegram.admin import set_admin_user
    from integrations.telegram.user_profiles import set_user_profile

    save_telegram_env({"TELEGRAM_BOT_TOKEN": "1:abc"}, profile="shared")
    set_user_profile("shared", 42, "alice")
    manager.create_profile("admin", inherit_global=True)
    set_admin_user("shared", 99, holix_profile="admin")

    updated = bootstrap_messenger_locales(TELEGRAM_PLATFORM, "shared")
    assert "shared" in updated
    assert "alice" in updated
    assert "admin" in updated
    assert LocaleStore("alice").get() == "ru"