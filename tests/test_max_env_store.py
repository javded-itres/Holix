"""Per-profile MAX env store."""

from __future__ import annotations

import pytest
from integrations.max.env_store import (
    max_env_path,
    read_max_env_values,
    save_max_env,
)


@pytest.fixture
def holix_home(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import cli.core as cli_core

    root = tmp_path / "holix"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("HOLIX_HOME", str(root))
    monkeypatch.setattr(cli_core, "HOLIX_HOME", root)
    monkeypatch.setattr(cli_core, "PROFILES_DIR", profiles)
    return root


def test_save_per_profile_env(holix_home) -> None:
    path = save_max_env(
        {
            "MAX_ACCESS_TOKEN": "a" * 20,
            "HOLIX_MAX_ALLOWED_USERS": "1,2",
            "HELIX_MAX_MODE": "polling",
        },
        profile="docs",
    )
    assert path == max_env_path("docs")
    assert path.is_file()
    values = read_max_env_values("docs")
    assert values["MAX_ACCESS_TOKEN"] == "a" * 20
    assert values["HOLIX_MAX_ALLOWED_USERS"] == "1,2"
    assert values["HOLIX_MAX_MODE"] == "polling"