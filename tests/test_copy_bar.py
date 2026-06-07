"""Tests for selection copy bar helpers."""

from __future__ import annotations

from textual.geometry import Offset
from textual.selection import Selection

from cli.tui.shared.copy_bar import selection_has_text


def test_selection_has_text_range():
    sel = Selection(Offset(0, 0), Offset(5, 2))
    assert selection_has_text(sel)


def test_selection_has_text_empty_cursor():
    sel = Selection(Offset(1, 1), Offset(1, 1))
    assert not selection_has_text(sel)


def test_selection_has_text_none():
    assert not selection_has_text(None)