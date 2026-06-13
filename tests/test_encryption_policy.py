"""Tests for global encryption policy modes."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.core import ProfileManager
from core.crypto.bootstrap import enable_profile_encryption
from core.crypto.policy import (
    EncryptionMode,
    is_encryption_runtime_active,
    is_profile_encryption_enabled,
    parse_encryption_mode,
    profile_has_crypto_metadata,
    require_encryption_enable_allowed,
)
from core.crypto.profile_crypto import ProfileCryptoError, create_profile_crypto


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_parse_encryption_mode_aliases() -> None:
    assert parse_encryption_mode("off") is EncryptionMode.OFF
    assert parse_encryption_mode("linux-production") is EncryptionMode.LINUX_PRODUCTION
    assert parse_encryption_mode("on") is EncryptionMode.ON


def test_runtime_inactive_on_mac_dev(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_ENCRYPTION_MODE", "linux-production")
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.setattr("core.crypto.policy.IS_LINUX", False)
    monkeypatch.setattr("core.crypto.policy.sys.platform", "darwin")
    manager = ProfileManager()
    manager.create_profile("alice", inherit_global=False)
    create_profile_crypto("alice", "unlock-key-alice-99")

    assert profile_has_crypto_metadata("alice")
    assert is_encryption_runtime_active() is False
    assert is_profile_encryption_enabled("alice") is False


def test_runtime_active_on_linux(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_ENCRYPTION_MODE", "linux-production")
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.setattr("core.crypto.policy.IS_LINUX", True)
    monkeypatch.setattr("core.crypto.policy.sys.platform", "linux")
    manager = ProfileManager()
    manager.create_profile("bob", inherit_global=False)
    create_profile_crypto("bob", "unlock-key-bob-1234")

    assert is_encryption_runtime_active() is True
    assert is_profile_encryption_enabled("bob") is True


def test_mode_off_disables_runtime(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_ENCRYPTION_MODE", "off")
    monkeypatch.setenv("HOLIX_ENV", "production")
    monkeypatch.setattr("core.crypto.policy.IS_LINUX", True)
    manager = ProfileManager()
    manager.create_profile("carol", inherit_global=False)
    create_profile_crypto("carol", "unlock-key-carol-88")

    assert is_encryption_runtime_active() is False
    assert is_profile_encryption_enabled("carol") is False


def test_mode_on_always_active(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_ENCRYPTION_MODE", "on")
    monkeypatch.setenv("HOLIX_ENV", "development")
    manager = ProfileManager()
    manager.create_profile("dave", inherit_global=False)
    create_profile_crypto("dave", "unlock-key-dave-11")

    assert is_encryption_runtime_active() is True
    assert is_profile_encryption_enabled("dave") is True


def test_enable_blocked_off(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_ENCRYPTION_MODE", "off")
    manager = ProfileManager()
    manager.create_profile("erin", inherit_global=False)

    with pytest.raises(ProfileCryptoError, match="disabled"):
        enable_profile_encryption(manager, "erin", "unlock-key-erin-55")


def test_enable_blocked_non_linux_production(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_ENCRYPTION_MODE", "linux-production")
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.setattr("core.crypto.policy.IS_LINUX", False)
    monkeypatch.setattr("core.crypto.policy.sys.platform", "darwin")
    manager = ProfileManager()
    manager.create_profile("frank", inherit_global=False)

    with pytest.raises(ProfileCryptoError, match="Linux hosts"):
        require_encryption_enable_allowed()


def test_enable_allowed_on_linux(holix_home, monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_ENCRYPTION_MODE", "linux-production")
    monkeypatch.setenv("HOLIX_ENV", "development")
    monkeypatch.setattr("core.crypto.policy.IS_LINUX", True)
    monkeypatch.setattr("core.crypto.policy.sys.platform", "linux")
    manager = ProfileManager()
    manager.create_profile("grace", inherit_global=False)

    require_encryption_enable_allowed()
    result = enable_profile_encryption(manager, "grace", "unlock-key-grace-42", encrypt_existing=False)
    assert result.profile == "grace"
    assert profile_has_crypto_metadata("grace")