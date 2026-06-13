"""Doctor checks for MAX messenger integration."""

from __future__ import annotations

import pytest
from cli.doctor.checks import _check_max


def _block_max_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "integrations.max.env_store.load_max_env_files",
        lambda *args, **kwargs: None,
    )


def test_max_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from integrations.max.config import MaxSettings

    _block_max_env(monkeypatch)
    for key in (
        "MAX_ACCESS_TOKEN",
        "HOLIX_MAX_ACCESS_TOKEN",
        "HELIX_MAX_ACCESS_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        "integrations.max.config.load_max_settings",
        lambda profile: MaxSettings(access_token="", profile=profile),
    )

    findings = _check_max("default")
    assert any(f.code == "max.not_configured" for f in findings)


def test_max_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_max_env(monkeypatch)
    monkeypatch.setenv("MAX_ACCESS_TOKEN", "short")

    findings = _check_max("default")
    assert any(f.code == "max.invalid_token" for f in findings)


def _clear_max_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "HOLIX_MAX_ALLOWED_USERS",
        "HELIX_MAX_ALLOWED_USERS",
        "HOLIX_MAX_ALLOW_ALL",
        "HELIX_MAX_ALLOW_ALL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_max_access_requests_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_max_env(monkeypatch)
    monkeypatch.setenv("MAX_ACCESS_TOKEN", "x" * 20)
    _clear_max_allowlist(monkeypatch)

    findings = _check_max("default")
    assert any(f.code == "max.access_requests" for f in findings)


def test_max_no_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_max_env(monkeypatch)
    monkeypatch.setenv("MAX_ACCESS_TOKEN", "x" * 20)
    monkeypatch.setenv("HOLIX_MAX_ACCESS_REQUESTS", "false")
    _clear_max_allowlist(monkeypatch)

    findings = _check_max("default")
    assert any(f.code == "max.no_allowlist" for f in findings)


def test_max_webhook_requires_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_max_env(monkeypatch)
    monkeypatch.setenv("MAX_ACCESS_TOKEN", "x" * 20)
    monkeypatch.setenv("HOLIX_MAX_ALLOWED_USERS", "42")
    monkeypatch.setenv("HOLIX_MAX_MODE", "webhook")
    monkeypatch.delenv("HOLIX_MAX_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("HELIX_MAX_WEBHOOK_URL", raising=False)

    findings = _check_max("default")
    assert any(f.code == "max.webhook_url_missing" for f in findings)


def test_max_webhook_https_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_max_env(monkeypatch)
    monkeypatch.setenv("MAX_ACCESS_TOKEN", "x" * 20)
    monkeypatch.setenv("HOLIX_MAX_ALLOWED_USERS", "42")
    monkeypatch.setenv("HOLIX_MAX_MODE", "webhook")
    monkeypatch.setenv("HOLIX_MAX_WEBHOOK_URL", "http://example.com/max/webhook")
    monkeypatch.setenv("HELIX_MAX_WEBHOOK_URL", "http://example.com/max/webhook")

    findings = _check_max("default")
    assert any(f.code == "max.webhook_not_https" for f in findings)


def test_max_allow_all_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_max_env(monkeypatch)
    monkeypatch.setenv("MAX_ACCESS_TOKEN", "x" * 20)
    monkeypatch.setenv("HELIX_MAX_ALLOW_ALL", "true")

    findings = _check_max("default")
    assert any(f.code == "max.allow_all" for f in findings)


def test_max_files_extra_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_max_env(monkeypatch)
    monkeypatch.setenv("MAX_ACCESS_TOKEN", "x" * 20)
    monkeypatch.setenv("HELIX_MAX_ALLOWED_USERS", "42")
    monkeypatch.setenv("HELIX_MAX_FILES_ENABLED", "true")
    monkeypatch.setattr(
        "integrations.max.config.max_files_extra_available",
        lambda: False,
    )

    findings = _check_max("default")
    assert any(f.code == "max.files_extra_missing" for f in findings)