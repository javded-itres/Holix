"""Gateway supervisor companion service rules."""

from __future__ import annotations

from pathlib import Path

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
    monkeypatch.delenv("HOLIX_TELEGRAM_AUTOSTART", raising=False)
    if telegram_aiogram_available():
        assert telegram_should_start() is True
    else:
        assert telegram_should_start() is False


def test_telegram_should_start_respects_autostart_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gateway-only Docker sets HOLIX_TELEGRAM_AUTOSTART=false."""
    _block_telegram_env_files(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("HOLIX_TELEGRAM_AUTOSTART", "false")
    assert telegram_should_start() is False


def test_docs_should_start_when_site_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = tmp_path / "holix-docs"
    site.mkdir()
    (site / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setenv("HOLIX_WEB_DOCS_DIR", str(site))
    assert docs_should_start() is True


def test_telegram_subprocess_sets_workspace_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = tmp_path / "Develop"
    ws.mkdir()
    captured: dict[str, object] = {}

    class _Proc:
        pid = 4242

    monkeypatch.setattr("cli.services.supervisor.telegram_enabled", lambda profile: True)
    monkeypatch.setattr("cli.services.supervisor.telegram_aiogram_available", lambda: True)
    monkeypatch.setattr(
        "cli.services.supervisor._terminate_stray_module_workers", lambda *a, **k: None
    )
    monkeypatch.setattr("cli.services.supervisor.update_telegram_pid", lambda *a, **k: None)
    monkeypatch.setattr(
        "core.project.workspace_root.profile_workspace_cwd", lambda profile: str(ws)
    )

    def fake_popen(cmd, env=None, cwd=None, **kwargs):
        captured["cwd"] = cwd
        captured["cmd"] = cmd
        return _Proc()

    monkeypatch.setattr("cli.services.supervisor.popen_background", fake_popen)
    from cli.services.supervisor import _telegram_subprocess

    proc = _telegram_subprocess("admin")
    assert proc is not None
    assert captured["cwd"] == str(ws)


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
    monkeypatch.delenv("HOLIX_MAX_AUTOSTART", raising=False)
    assert max_should_poll() is True
    assert max_should_webhook() is False


def test_max_allows_polling_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit HOLIX_MAX_MODE=polling is honored even in production (gateway companion)."""
    _block_max_env_files(monkeypatch)
    monkeypatch.setenv("HOLIX_MAX_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("HOLIX_MAX_MODE", "polling")
    monkeypatch.setenv("HOLIX_ENV", "production")
    monkeypatch.delenv("HOLIX_MAX_AUTOSTART", raising=False)
    assert max_should_webhook() is False
    assert max_should_poll() is True


def test_max_should_poll_respects_autostart_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_max_env_files(monkeypatch)
    monkeypatch.setenv("HOLIX_MAX_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("HOLIX_MAX_MODE", "polling")
    monkeypatch.setenv("HOLIX_MAX_AUTOSTART", "false")
    assert max_should_poll() is False
