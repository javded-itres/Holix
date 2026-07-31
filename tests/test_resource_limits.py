"""Global CPU/RAM resource limits for Studio processes and Docker."""

from __future__ import annotations

from pathlib import Path

import pytest
from core.runtime import resource_limits as rl


@pytest.fixture()
def limits_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.setattr(rl, "resource_limits_path", lambda: tmp_path / "global" / "resource_limits.json")
    (tmp_path / "global").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_defaults_and_save(limits_home: Path) -> None:
    cfg = rl.load_resource_limits()
    assert cfg["enabled"] is True
    assert cfg["docker"]["cpus"] == 1.0
    assert cfg["docker"]["memory_mb"] == 512
    assert cfg["docker"]["block_public_db_ports"] is True

    saved = rl.save_resource_limits(
        {
            "docker": {"cpus": 0.5, "memory_mb": 256},
            "process": {"memory_mb": 128, "cpu_percent": 50},
        }
    )
    assert saved["docker"]["cpus"] == 0.5
    assert saved["docker"]["memory_mb"] == 256
    assert saved["process"]["memory_mb"] == 128
    reloaded = rl.load_resource_limits()
    assert reloaded["docker"]["cpus"] == 0.5


def test_docker_update_args(limits_home: Path) -> None:
    rl.save_resource_limits({"enabled": True, "docker": {"cpus": 1, "memory_mb": 512, "pids_limit": 100}})
    args = rl.docker_update_args()
    assert "--cpus" in args
    assert "--memory" in args
    assert "512m" in args
    assert "--pids-limit" in args

    rl.save_resource_limits({"enabled": False})
    assert rl.docker_update_args() == []


def test_public_db_port_scan() -> None:
    text = """
services:
  db:
    image: postgres:14
    ports:
      - "5432:5432"
      - "127.0.0.1:5433:5432"
      - "0.0.0.0:3306:3306"
"""
    found = rl.find_public_db_port_publishes(text)
    assert any("5432" in f for f in found)
    assert any("3306" in f for f in found)
    # loopback only should not appear as bad for 5433
    assert not any("5433" in f and "127.0.0.1" not in f for f in found if "127.0.0.1" in f)


def test_assert_compose_public_db_policy(tmp_path: Path, limits_home: Path) -> None:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "services:\n  db:\n    ports:\n      - '0.0.0.0:5432:5432'\n",
        encoding="utf-8",
    )
    rl.save_resource_limits({"enabled": True, "docker": {"block_public_db_ports": True}})
    with pytest.raises(ValueError, match="Public database"):
        rl.assert_compose_public_db_policy(compose)

    safe = tmp_path / "compose.yml"
    safe.write_text(
        "services:\n  db:\n    ports:\n      - '127.0.0.1:5432:5432'\n",
        encoding="utf-8",
    )
    rl.assert_compose_public_db_policy(safe)  # no raise


def test_memory_parse() -> None:
    assert rl.parse_memory_to_mb("512m") == 512
    assert rl.parse_memory_to_mb("1g") == 1024
    assert rl.memory_mb_to_docker(2048) == "2g"
    assert rl.memory_mb_to_docker(512) == "512m"
