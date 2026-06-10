"""Gateway + documentation companion options."""

from __future__ import annotations

import inspect
import re

from cli.commands import gateway as gateway_cmd
from cli.main import app
from typer.testing import CliRunner


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_gateway_start_help_lists_with_docs() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["gateway", "start", "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    text = _plain(result.stdout)
    assert "with-docs" in text
    assert "docs-port" in text


def test_gateway_start_accepts_with_docs_flag() -> None:
    params = inspect.signature(gateway_cmd.gateway_start).parameters
    assert "with_docs" in params
    assert "docs_port" in params