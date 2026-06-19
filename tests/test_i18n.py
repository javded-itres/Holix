"""Tests for UI locale store and translations."""

from __future__ import annotations

from pathlib import Path

import cli.core as cli_core
import pytest
from core.i18n import LocaleStore, host_locale, set_host_locale, t
from core.project.init_prompt import build_init_user_message
from core.prompt_builder import build_system_prompt


def _patch_holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "holix"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("HOLIX_HOME", str(root))
    monkeypatch.setattr(cli_core, "HOLIX_HOME", root)
    monkeypatch.setattr(cli_core, "PROFILES_DIR", profiles)
    return root


class _FakeHost:
    def __init__(self, profile: str = "i18n_test") -> None:
        self.profile = profile


def test_default_locale_is_en(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_holix_home(tmp_path, monkeypatch)
    store = LocaleStore("default_en")
    assert store.get() == "en"
    assert t("cleared", store.get()) == "Chat cleared"


def test_set_locale_ru(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_holix_home(tmp_path, monkeypatch)
    store = LocaleStore("default_ru")
    assert store.set("ru") == "ru"
    assert store.get() == "ru"
    assert t("cleared", "ru") == "Чат очищен"


def test_lang_set_message_no_locale_kwarg_conflict() -> None:
    assert t("lang.set", "en", code="EN") == "Interface language set to EN"
    assert t("lang.set", "ru", code="RU") == "Язык интерфейса: RU"


def test_set_locale_rejects_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_holix_home(tmp_path, monkeypatch)
    store = LocaleStore("default_bad")
    with pytest.raises(ValueError):
        store.set("de")


def test_host_locale_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_holix_home(tmp_path, monkeypatch)
    host = _FakeHost("host_helpers")
    assert host_locale(host) == "en"
    assert set_host_locale(host, "ru") == "ru"
    assert host_locale(host) == "ru"


def test_init_prompt_uses_profile_locale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_holix_home(tmp_path, monkeypatch)
    LocaleStore("init_ru").set("ru")
    msg = build_init_user_message(profile_name="init_ru")
    assert "глубокую инициализацию проекта" in msg.lower()
    assert "только на русском" in msg.lower() or "пиши на русском" in msg.lower()
    assert "/lang ru" in msg.lower()

    en_msg = build_init_user_message(locale="en")
    assert "deep project onboarding" in en_msg.lower()
    assert "interface language to english" in en_msg.lower()


def test_prompt_includes_russian_instruction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_holix_home(tmp_path, monkeypatch)
    LocaleStore("work").set("ru")
    prompt = build_system_prompt(
        tools_description="- **read_file**: read",
        active_skills=[],
        profile_name="work",
    )
    assert "только на русском" in prompt.lower()
    assert "/lang ru" in prompt.lower()
    assert prompt.strip().startswith("## Язык")