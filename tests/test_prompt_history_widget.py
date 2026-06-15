"""Prompt history label formatting."""

from __future__ import annotations

from cli.tui.code.widgets.prompt_history import format_history_label


def test_format_history_label_collapses_whitespace():
    assert format_history_label("hello\nworld") == "hello world"


def test_format_history_label_truncates():
    long = "x" * 120
    out = format_history_label(long, max_len=20)
    assert len(out) == 20
    assert out.endswith("…")