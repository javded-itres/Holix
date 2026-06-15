"""holix launch setup wizard tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from cli.launch import setup_wizard
from core.external_cli.registry import get_cli_spec


@pytest.fixture
def holix_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "holix"
    home.mkdir()
    monkeypatch.setenv("HOLIX_HOME", str(home))
    return home


def test_binary_installed_checks_binary_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = get_cli_spec("opencode")
    assert spec is not None
    install_dir = tmp_path / ".opencode" / "bin"
    install_dir.mkdir(parents=True)
    binary = install_dir / "opencode"
    binary.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr(setup_wizard.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(
        setup_wizard,
        "_install_path_dirs",
        lambda: str(install_dir),
    )

    assert setup_wizard._binary_installed(spec) == str(binary)


def test_try_install_runs_command(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = get_cli_spec("opencode")
    assert spec is not None
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(setup_wizard.shutil, "which", lambda name, path=None: "/bin/bash")
    monkeypatch.setattr(setup_wizard.subprocess, "run", fake_run)
    monkeypatch.setattr(setup_wizard, "_binary_installed", lambda _spec: "/tmp/.opencode/bin/opencode")

    assert setup_wizard._try_install("opencode") is True
    assert calls == [["bash", "-c", "curl -fsSL https://opencode.ai/install | bash"]]


def test_try_install_without_commands_only_shows_hint(capsys) -> None:
    assert setup_wizard._try_install("gigacode") is False


def test_opencode_has_install_commands() -> None:
    spec = get_cli_spec("opencode")
    assert spec is not None
    assert spec.install_commands
    assert spec.binary_paths