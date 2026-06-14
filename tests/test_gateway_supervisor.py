"""Gateway supervisor companion service rules."""

from __future__ import annotations

import pytest
from cli.services.supervisor import docs_should_start, telegram_enabled, telegram_should_start
from integrations.max.gateway_routes import max_enabled, max_should_poll, max_should_webhook
from integrations.telegram.config import load_telegram_settings, telegram_aiogram_available


def _block_telegram_env_files(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid loading the developer's real ~/.holix/telegram.env during tests."""
    monkeypatch.setattr(
        "integrations.telegram.env_store.load_telegram_env_files",
        lambda profile=None: None,
    )


def test_telegram_enabled_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_telegram_env_files(monkeypatch)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("HOLIX_TELEGRAM_BOT_TOKEN", raising=False)
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


def _block_max_env_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "integrations.max.env_store.load_max_env_files",
        lambda profile=None: None,
    )


def test_max_enabled_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.max.config import MaxSettings

    _block_max_env_files(monkeypatch)
    monkeypatch.delenv("MAX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HOLIX_MAX_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(
        "integrations.max.gateway_routes.load_max_settings",
        lambda profile="default": MaxSettings(access_token="", profile=profile),
    )
    assert max_enabled() is False


def test_max_should_webhook_requires_mode_and_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_max_env_files(monkeypatch)
    monkeypatch.setenv("HOLIX_MAX_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("HOLIX_MAX_MODE", "webhook")
    monkeypatch.delenv("HOLIX_ENV", raising=False)
    assert max_should_webhook() is True
    assert max_should_poll() is False


def test_max_should_poll_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_max_env_files(monkeypatch)
    monkeypatch.setenv("HOLIX_MAX_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("HOLIX_MAX_MODE", "polling")
    monkeypatch.setenv("HOLIX_ENV", "development")
    assert max_should_poll() is True
    assert max_should_webhook() is False


def test_max_forces_webhook_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_max_env_files(monkeypatch)
    monkeypatch.setenv("HOLIX_MAX_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("HOLIX_MAX_MODE", "polling")
    monkeypatch.setenv("HOLIX_ENV", "production")
    assert max_should_webhook() is True
    assert max_should_poll() is False