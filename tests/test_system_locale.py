"""Tests for OS locale detection and install language resolution."""

from __future__ import annotations

import pytest
from core.i18n.system_locale import (
    apply_profile_locale,
    detect_system_locale,
    resolve_install_locale,
)


def test_detect_system_locale_from_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANG", "ru_RU.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    assert detect_system_locale() == "ru"


def test_detect_system_locale_en_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert detect_system_locale() == "en"


def test_resolve_install_locale_russian_system(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANG", "ru_RU.UTF-8")
    assert resolve_install_locale(interactive=False) == "ru"


def test_resolve_install_locale_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert resolve_install_locale(explicit="ru", interactive=False) == "ru"


def test_resolve_install_locale_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("HOLIX_BOOTSTRAP_LANG", "ru")
    assert resolve_install_locale(interactive=False) == "ru"


def test_apply_profile_locale(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import cli.core as cli_core

    root = tmp_path / "holix"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("HOLIX_HOME", str(root))
    monkeypatch.setattr(cli_core, "HOLIX_HOME", root)
    monkeypatch.setattr(cli_core, "PROFILES_DIR", profiles)

    apply_profile_locale("ru", "default", "admin")

    from core.i18n import LocaleStore

    assert LocaleStore("default").get() == "ru"
    assert LocaleStore("admin").get() == "ru"