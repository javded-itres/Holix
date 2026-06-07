"""Tests for code TUI context usage bar."""

from __future__ import annotations

from cli.tui.code.widgets.context_bar import CodeContextBar


def test_context_bar_usage_renders_blocks():
    bar = CodeContextBar()
    bar.set_usage(50.0, "yellow", {"used": 5000, "total": 10000, "percent": 50.0})
    text = str(bar.render())
    assert "Context:" in text
    assert "50%" in text
    assert "█" in text
    assert "░" in text


def test_context_bar_placeholder():
    bar = CodeContextBar()
    bar.set_placeholder()
    assert "──" in str(bar.render())