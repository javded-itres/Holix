"""Session permission presets."""

from __future__ import annotations

from core.security.permission_preset import (
    auto_allow_high,
    default_preset,
    get_preset,
    read_only_block_reason,
    reset_permission_presets,
    set_preset,
)


def setup_function() -> None:
    reset_permission_presets()


def test_default_follows_jail(monkeypatch) -> None:
    monkeypatch.delenv("HOLIX_PERMISSION_MODE", raising=False)
    assert default_preset(jail_enabled=True) == "workspace-write"
    assert default_preset(jail_enabled=False) == "danger-full-access"


def test_set_and_get_roundtrip() -> None:
    assert set_preset("default", "sess", "read-only") == "read-only"
    assert get_preset("default", "sess", jail_enabled=False) == "read-only"
    reason = read_only_block_reason("write_file", profile="default", conversation_id="sess")
    assert reason and "read-only" in reason
    assert read_only_block_reason("read_file", profile="default", conversation_id="sess") is None


def test_env_override(monkeypatch) -> None:
    monkeypatch.setenv("HOLIX_PERMISSION_MODE", "workspace-write")
    assert default_preset(jail_enabled=False) == "workspace-write"


def test_auto_allow_high_only_when_pinned() -> None:
    assert auto_allow_high(profile="default", conversation_id="sess") is False
    set_preset("default", "sess", "danger-full-access")
    assert auto_allow_high(profile="default", conversation_id="sess") is True
    set_preset("default", "sess", "workspace-write")
    assert auto_allow_high(profile="default", conversation_id="sess") is False
