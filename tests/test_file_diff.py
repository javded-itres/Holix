"""Tests for file diff formatting."""

from __future__ import annotations

import os
import tempfile

import pytest
from cli.tui.shared.formatters import split_write_file_result
from core.tools.file_diff import (
    DIFF_SEPARATOR,
    format_write_file_result,
    summarize_file_write,
    unified_diff_text,
)
from core.tools.file_ops import WriteFileTool


def test_unified_diff_shows_changes():
    diff = unified_diff_text("foo.py", "a\nb\n", "a\nc\n")
    assert "--- a/foo.py" in diff
    assert "+++ b/foo.py" in diff
    assert "-b" in diff
    assert "+c" in diff


def test_format_write_file_result_includes_separator():
    body = format_write_file_result("x.py", "old\n", "new\n")
    assert "Updated x.py" in body
    assert DIFF_SEPARATOR in body
    summary, diff = split_write_file_result(body)
    assert summary.startswith("Updated")
    assert diff and "+new" in diff


def test_new_file_summary():
    assert "Created" in summarize_file_write("new.py", None, "line1\nline2\n")


@pytest.mark.asyncio
async def test_write_file_returns_diff():
    tool = WriteFileTool()
    with tempfile.TemporaryDirectory() as temp_dir:
        path = os.path.join(temp_dir, "sample.py")
        first = await tool.execute(path, "x = 1\n")
        assert "Created" in first
        assert DIFF_SEPARATOR in first

        second = await tool.execute(path, "x = 2\n")
        assert "Updated" in second
        summary, diff = split_write_file_result(second)
        assert "-x = 1" in diff or "-x = 1\n" in diff
        assert "+x = 2" in diff or "+x = 2\n" in diff