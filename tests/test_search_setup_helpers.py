"""Tests for shared web search setup helpers."""

from __future__ import annotations

import pytest
from core.search.config import SearchConfig
from core.search.setup_helpers import (
    build_search_config,
    default_providers_from_env,
    save_profile_search,
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


def test_default_providers_from_env_prefers_firecrawl_and_searxng(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080")
    assert default_providers_from_env() == ["firecrawl", "searxng"]


def test_default_providers_falls_back_to_duckduckgo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("SEARXNG_BASE_URL", raising=False)
    assert default_providers_from_env() == ["duckduckgo"]


def test_build_search_config_enables_providers_and_env_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://searx.local")
    data = build_search_config(
        ["firecrawl", "searxng"],
        env_values={
            "FIRECRAWL_API_KEY": "fc-test",
            "SEARXNG_BASE_URL": "http://searx.local",
        },
    )
    assert data["providers"] == ["firecrawl", "searxng"]
    assert data["firecrawl"]["enabled"] is True
    assert data["firecrawl"]["api_key"] == "${FIRECRAWL_API_KEY}"
    assert data["searxng"]["base_url"] == "${SEARXNG_BASE_URL}"
    assert data["duckduckgo"]["enabled"] is False
    sc = SearchConfig.from_dict(data)
    assert sc.enabled_providers() == ["firecrawl", "searxng"]


def test_save_profile_search_persists_to_profile(holix_home) -> None:
    from cli.core import ProfileManager
    from core.search.setup_helpers import load_profile_search

    manager = ProfileManager()
    manager.create_profile("main", inherit_global=True)
    data = build_search_config(["firecrawl"], env_values={"FIRECRAWL_API_KEY": "x"})
    save_profile_search("main", data)
    loaded = load_profile_search("main")
    assert SearchConfig.from_dict(loaded).enabled_providers() == ["firecrawl"]