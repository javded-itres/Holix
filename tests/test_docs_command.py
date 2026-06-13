"""Tests for holix docs command."""

from __future__ import annotations

from pathlib import Path

from cli.main import app
from cli.services.docs_site import build_docs_site, resolve_web_docs_dir
from typer.testing import CliRunner


def test_resolve_web_docs_dir_finds_index() -> None:
    root = resolve_web_docs_dir()
    assert (root / "index.html").is_file()
    assert (root / "search-index.json").is_file()


def test_build_docs_site() -> None:
    root = build_docs_site()
    assert (root / "nav.json").is_file()
    assert (root / "content" / "en" / "CLI.md").is_file()


def test_docs_help_lists_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["docs", "--help"])
    assert result.exit_code == 0
    assert "serve" in result.stdout
    assert "build" in result.stdout


def test_docs_build_cli() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["docs", "build"])
    assert result.exit_code == 0
    root = resolve_web_docs_dir()
    assert Path(root / "search-index.json").stat().st_size > 1000
    assert (root / "search-chunks.json").is_file()
    assert (root / "search-vectors.npz").is_file()