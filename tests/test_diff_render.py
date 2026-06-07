"""Tests for TUI diff rendering."""

from __future__ import annotations

from rich.panel import Panel

from cli.tui.shared.diff_render import render_unified_diff
from cli.tui.shared.formatters import format_write_file_diff_display
from core.tools.file_diff import format_write_file_result


def test_render_unified_diff_returns_panel():
    diff = format_write_file_result("app.py", "a = 1\n", "a = 2\n").split("--- diff ---\n", 1)[1]
    panel = render_unified_diff(diff, path="app.py")
    assert isinstance(panel, Panel)
    title = str(panel.title)
    assert "app.py" in title
    assert "+1" in title or "−1" in title


def test_format_write_file_diff_display_delegates():
    diff = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n"
    panel = format_write_file_diff_display(diff, path="x")
    assert isinstance(panel, Panel)