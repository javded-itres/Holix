"""holix --version / holix version (no profile required)."""

from __future__ import annotations

from cli.main import _package_version, app
from typer.testing import CliRunner


def test_version_flag_prints_package_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert _package_version() in result.stdout
    assert result.stdout.strip().startswith("Holix ")


def test_version_short_flag() -> None:
    result = CliRunner().invoke(app, ["-V"])
    assert result.exit_code == 0
    assert _package_version() in result.stdout


def test_version_subcommand() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert "Version:" in result.stdout
    assert _package_version() in result.stdout
