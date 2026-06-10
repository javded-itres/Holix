"""Tests for global settings inheritance across profiles."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from cli.core import ProfileConfig, ProfileManager
from core.env_loader import bootstrap_profile_env, profile_env_path
from core.global_config import (
    ensure_global_config,
    ensure_global_env_template,
    extract_profile_overrides,
    global_config_path,
    global_env_path,
    load_global_config_resolved,
    merge_global_with_profile,
)


@pytest.fixture
def helix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_global_config_merge_profile_overrides(helix_home: Path) -> None:
    global_data = {"model": "global-model", "temperature": 0.5, "providers": {"litellm": {"default_model": "a"}}}
    profile_data = {"profile_name": "alice", "model": "alice-model"}
    merged = merge_global_with_profile(global_data, profile_data)
    assert merged["model"] == "alice-model"
    assert merged["temperature"] == 0.5
    assert merged["providers"]["litellm"]["default_model"] == "a"


def test_load_profile_inherits_global_model(helix_home: Path) -> None:
    ensure_global_config()
    global_config_path().write_text(
        "model: shared-llm\ntemperature: 0.2\n",
        encoding="utf-8",
    )

    manager = ProfileManager()
    manager.create_profile("alice", inherit_global=True)
    (manager.get_profile_dir("alice") / "config.yaml").write_text(
        "profile_name: alice\n",
        encoding="utf-8",
    )

    cfg = manager.load_profile("alice")
    assert cfg.model == "shared-llm"
    assert cfg.temperature == 0.2


def test_profile_override_beats_global(helix_home: Path) -> None:
    ensure_global_config()
    global_config_path().write_text("model: global-model\n", encoding="utf-8")

    manager = ProfileManager()
    manager.create_profile("bob", inherit_global=True)
    (manager.get_profile_dir("bob") / "config.yaml").write_text(
        "profile_name: bob\nmodel: bob-model\n",
        encoding="utf-8",
    )

    cfg = manager.load_profile("bob")
    assert cfg.model == "bob-model"


def test_save_profile_stores_only_overrides(helix_home: Path) -> None:
    ensure_global_config()
    global_config_path().write_text(
        "model: global-model\ntemperature: 0.7\n",
        encoding="utf-8",
    )

    manager = ProfileManager()
    cfg = ProfileConfig(profile_name="carol", model="carol-model", temperature=0.7)
    manager.create_profile("carol", config=cfg, inherit_global=False)
    manager.save_profile("carol", cfg, storage_mode="sparse")

    stored = yaml.safe_load((manager.get_profile_dir("carol") / "config.yaml").read_text(encoding="utf-8"))
    assert stored["model"] == "carol-model"
    assert "temperature" not in stored


def test_clean_profile_does_not_inherit_env_copy(helix_home: Path) -> None:
    ensure_global_env_template()
    global_env_path().write_text("HELIX_TEST_VAR=global\n", encoding="utf-8")

    manager = ProfileManager()
    manager.create_profile("clean", inherit_global=False)
    profile_env = profile_env_path("clean")
    assert "global" not in profile_env.read_text(encoding="utf-8")

    bootstrap_profile_env("clean", force=True)
    assert os.environ.get("HELIX_TEST_VAR") == "global"


def test_inherit_profile_env_runtime_fallback(
    helix_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HELIX_TEST_VAR", raising=False)
    ensure_global_env_template()
    global_env_path().write_text("HELIX_TEST_VAR=global\n", encoding="utf-8")

    manager = ProfileManager()
    manager.create_profile("inherit", inherit_global=True)
    profile_env_path("inherit").write_text(
        "# overrides only\nHELIX_TEST_VAR=profile\n",
        encoding="utf-8",
    )

    bootstrap_profile_env("inherit", force=True)
    assert os.environ.get("HELIX_TEST_VAR") == "profile"


def test_extract_profile_overrides_nested_providers(helix_home: Path) -> None:
    global_data = {
        "providers": {
            "litellm": {"default_model": "shared", "base_url": "http://localhost:4000/v1"},
        }
    }
    resolved = {
        "profile_name": "x",
        "providers": {
            "litellm": {"default_model": "custom", "base_url": "http://localhost:4000/v1"},
        },
    }
    out = extract_profile_overrides(resolved, global_data)
    assert out["providers"]["litellm"]["default_model"] == "custom"
    assert "base_url" not in out["providers"]["litellm"]


def test_global_change_applies_to_inherited_profile(helix_home: Path) -> None:
    ensure_global_config()
    global_config_path().write_text("model: v1\n", encoding="utf-8")

    manager = ProfileManager()
    manager.create_profile("dyn", inherit_global=True)
    assert manager.load_profile("dyn").model == "v1"

    global_config_path().write_text("model: v2\n", encoding="utf-8")
    assert manager.load_profile("dyn").model == "v2"


def test_ensure_global_seeds_from_default_profile(helix_home: Path) -> None:
    manager = ProfileManager()
    manager.create_profile("default", inherit_global=False)
    (manager.get_profile_dir("default") / "config.yaml").write_text(
        "profile_name: default\nmodel: from-default\n",
        encoding="utf-8",
    )

    global_config_path().unlink(missing_ok=True)
    path = ensure_global_config(seed_from_profile="default")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["model"] == "from-default"
    assert "profile_name" not in data