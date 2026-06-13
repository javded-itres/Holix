"""Production admin profile seeding from default."""

from __future__ import annotations

import pytest
import yaml
from cli.core import ProfileManager
from core.profile_admin_seed import (
    copy_profile_settings_from_source,
    ensure_admin_profile_from_default,
    is_production_env,
)


@pytest.fixture
def holix_home(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import cli.core as cli_core

    root = tmp_path / "holix"
    profiles = root / "profiles"
    profiles.mkdir(parents=True)
    (root / "global").mkdir(parents=True)
    (root / "global" / "config.yaml").write_text("model: global-model\n", encoding="utf-8")
    monkeypatch.setenv("HOLIX_HOME", str(root))
    monkeypatch.setattr(cli_core, "HOLIX_HOME", root)
    monkeypatch.setattr(cli_core, "PROFILES_DIR", profiles)
    return root


def test_is_production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_ENV", "production")
    assert is_production_env()
    monkeypatch.setenv("HOLIX_ENV", "development")
    assert not is_production_env()


def test_ensure_admin_creates_and_copies_from_default(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_ENV", "production")
    manager = ProfileManager()
    manager.create_profile("default", inherit_global=True)
    default_cfg = manager.load_profile("default")
    default_cfg.model = "copied-model"
    default_cfg.temperature = 0.42
    manager.save_profile("default", default_cfg)

    result = ensure_admin_profile_from_default(manager=manager)
    assert result == "admin"
    assert manager.profile_exists("admin")

    admin_cfg = manager.load_profile("admin")
    assert admin_cfg.model == "copied-model"
    assert admin_cfg.temperature == 0.42

    raw = yaml.safe_load((manager.get_profile_dir("admin") / "config.yaml").read_text(encoding="utf-8"))
    assert raw.get("model") == "copied-model"


def test_no_seed_outside_production(holix_home, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_ENV", "development")
    manager = ProfileManager()
    manager.create_profile("default", inherit_global=True)

    assert ensure_admin_profile_from_default(manager=manager) is None
    assert not manager.profile_exists("admin")


def test_copy_profile_settings_updates_existing_admin(holix_home) -> None:
    manager = ProfileManager()
    manager.create_profile("default", inherit_global=True)
    manager.create_profile("admin", inherit_global=True)

    default_cfg = manager.load_profile("default")
    default_cfg.max_steps = 17
    manager.save_profile("default", default_cfg)

    assert copy_profile_settings_from_source(
        manager,
        source_profile="default",
        target_profile="admin",
    )
    assert manager.load_profile("admin").max_steps == 17