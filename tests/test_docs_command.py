"""Tests for holix docs command."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.main import app
from cli.services.docs_site import build_docs_site, resolve_web_docs_dir
from typer.testing import CliRunner

_MINIMAL_BUILD_PY = """\
from pathlib import Path
import json
root = Path(__file__).resolve().parent
(root / "nav.json").write_text("[]", encoding="utf-8")
(root / "search-index.json").write_text(json.dumps({"pages": ["x"] * 200}), encoding="utf-8")
(root / "search-chunks.json").write_text("[]", encoding="utf-8")
(root / "search-vectors.npz").write_bytes(b"\\x93NUMPY")
"""


@pytest.fixture
def docs_site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    site = tmp_path / "holix-docs"
    site.mkdir()
    (site / "index.html").write_text("<html></html>", encoding="utf-8")
    (site / "search-index.json").write_text("{}", encoding="utf-8")
    (site / "content" / "en").mkdir(parents=True)
    (site / "content" / "en" / "CLI.md").write_text("# CLI\n", encoding="utf-8")
    (site / "build.py").write_text(_MINIMAL_BUILD_PY, encoding="utf-8")
    monkeypatch.setenv("HOLIX_WEB_DOCS_DIR", str(site))
    return site


def test_resolve_web_docs_dir_finds_index(docs_site: Path) -> None:
    root = resolve_web_docs_dir()
    assert root == docs_site.resolve()
    assert (root / "index.html").is_file()
    assert (root / "search-index.json").is_file()


def test_build_docs_site(docs_site: Path) -> None:
    root = build_docs_site()
    assert (root / "nav.json").is_file()
    assert (root / "content" / "en" / "CLI.md").is_file()


def test_docs_help_lists_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["docs", "--help"])
    assert result.exit_code == 0
    assert "serve" in result.stdout
    assert "build" in result.stdout


def test_docs_build_cli(docs_site: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["docs", "build"])
    assert result.exit_code == 0
    root = resolve_web_docs_dir()
    assert Path(root / "search-index.json").stat().st_size > 1000
    assert (root / "search-chunks.json").is_file()
    assert (root / "search-vectors.npz").is_file()