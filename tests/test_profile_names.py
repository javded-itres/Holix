"""Tests for profile name validation (CodeQL path-injection guard)."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.profile.names import (
    ProfileNameError,
    assert_under_profiles_root,
    profile_dir_for_name,
    resolve_workspace_root,
    validate_profile_name,
)


def test_validate_profile_name_accepts_safe_names() -> None:
    assert validate_profile_name("admin") == "admin"
    assert validate_profile_name("  alice-bob_1  ") == "alice-bob_1"
    assert validate_profile_name(None) == "default"
    assert validate_profile_name("") == "default"


@pytest.mark.parametrize(
    "bad",
    ["../etc", "foo/bar", "..", ".", "bad name", "x" * 70, "-start"],
)
def test_validate_profile_name_rejects_unsafe(bad: str) -> None:
    with pytest.raises(ProfileNameError):
        validate_profile_name(bad)


def test_profile_dir_for_name_under_profiles_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))
    path = profile_dir_for_name("alice")
    assert path == (tmp_path / "profiles" / "alice").resolve()


def test_resolve_workspace_root_rejects_traversal() -> None:
    with pytest.raises(ProfileNameError):
        resolve_workspace_root(Path("../outside"))


def test_assert_under_profiles_root_rejects_escape(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ProfileNameError):
        assert_under_profiles_root(outside)