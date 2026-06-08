"""Gateway supervisor companion service rules."""

from __future__ import annotations

import pytest
from cli.services.supervisor import docs_should_start, telegram_enabled, telegram_should_start
from integrations.telegram.config import load_telegram_settings, telegram_aiogram_available


def _block_telegram_env_files(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid loading the developer's real ~/.helix/telegram.env during tests."""
    monkeypatch.setattr(
        "integrations.telegram.env_store.load_telegram_env_files",
        lambda profile=None: None,
    )


def test_telegram_enabled_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_telegram_env_files(monkeypatch)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("HELIX_TELEGRAM_BOT_TOKEN", raising=False)
    assert telegram_enabled() is False


def test_telegram_enabled_with_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_telegram_env_files(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    assert telegram_enabled() is True


def test_telegram_should_start_requires_aiogram(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_telegram_env_files(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    if telegram_aiogram_available():
        assert telegram_should_start() is True
    else:
        assert telegram_should_start() is False


def test_docs_should_start_in_repo() -> None:
    assert docs_should_start() is True


def test_load_telegram_settings_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_telegram_env_files(monkeypatch)
    settings = load_telegram_settings("work")
    assert settings.profile == "work"