"""Gateway configure helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.commands.gateway_configure import (
    GatewayProfileConfig,
    list_configured_gateway_ports,
    load_effective_gateway_config,
    suggest_gateway_port,
)

_GATEWAY_ENV_KEYS = (
    "HELIX_GATEWAY_HOST",
    "HELIX_GATEWAY_PORT",
    "HELIX_REQUIRE_AUTH",
    "HELIX_GATEWAY_WITH_DOCS",
    "HELIX_GATEWAY_DOCS",
    "HELIX_DOCS_HOST",
    "HELIX_DOCS_PORT",
)


def _clear_gateway_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _GATEWAY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _seed_profile(profiles_root: Path, name: str, env_body: str) -> None:
    profile_dir = profiles_root / name
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "config.yaml").write_text("model: test\n", encoding="utf-8")
    (profile_dir / ".env").write_text(env_body, encoding="utf-8")


def test_list_configured_gateway_ports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_gateway_env(monkeypatch)
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))
    profiles = tmp_path / "profiles"
    _seed_profile(profiles, "alice", "HELIX_GATEWAY_PORT=8001\n")
    _seed_profile(profiles, "bob", "HELIX_GATEWAY_PORT=8002\n")

    ports = list_configured_gateway_ports()
    assert ports["alice"] == 8001
    assert ports["bob"] == 8002


def test_list_configured_gateway_ports_excludes_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_gateway_env(monkeypatch)
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))
    profiles = tmp_path / "profiles"
    _seed_profile(profiles, "alice", "HELIX_GATEWAY_PORT=8001\n")
    _seed_profile(profiles, "bob", "HELIX_GATEWAY_PORT=8002\n")

    ports = list_configured_gateway_ports(exclude_profile="alice")
    assert "alice" not in ports
    assert ports["bob"] == 8002


def test_suggest_gateway_port_skips_other_profiles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_gateway_env(monkeypatch)
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))
    profiles = tmp_path / "profiles"
    _seed_profile(profiles, "alice", "HELIX_GATEWAY_PORT=8000\n")
    _seed_profile(profiles, "bob", "")

    port = suggest_gateway_port("127.0.0.1", profile="bob", base_port=8000)
    assert port != 8000


def test_load_effective_gateway_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_gateway_env(monkeypatch)
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))
    _seed_profile(
        tmp_path / "profiles",
        "work",
        (
            "HELIX_GATEWAY_HOST=0.0.0.0\n"
            "HELIX_GATEWAY_PORT=9001\n"
            "HELIX_REQUIRE_AUTH=true\n"
        ),
    )

    cfg = load_effective_gateway_config("work")
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 9001
    assert cfg.require_auth is True
    assert cfg.profile == "work"


def test_save_gateway_env_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_gateway_env(monkeypatch)
    monkeypatch.setenv("HELIX_HOME", str(tmp_path))
    from cli.commands.gateway_configure import _save_gateway_env

    _seed_profile(tmp_path / "profiles", "demo", "# demo\n")
    env_path = tmp_path / "profiles" / "demo" / ".env"

    cfg = GatewayProfileConfig(
        profile="demo",
        host="127.0.0.1",
        port=8010,
        require_auth=True,
        with_docs=True,
        docs_host="127.0.0.1",
        docs_port=8088,
        env_path=str(env_path),
    )
    _save_gateway_env("demo", cfg)
    loaded = load_effective_gateway_config("demo")
    assert loaded.port == 8010
    assert loaded.require_auth is True
    assert loaded.with_docs is True
    assert loaded.docs_port == 8088