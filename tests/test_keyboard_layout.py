"""Tests for macOS / RU keyboard layout helpers."""

from __future__ import annotations

import sys

import pytest

from cli.shared import slash_input as si
from cli.tui.shared import keyboard_layout as kl


def _patch_macos(monkeypatch: pytest.MonkeyPatch, *, value: bool) -> None:
    monkeypatch.setattr(kl, "is_macos", lambda: value)
    monkeypatch.setattr(si, "is_macos", lambda: value)


@pytest.fixture
def darwin(monkeypatch):
    _patch_macos(monkeypatch, value=True)


@pytest.fixture
def linux(monkeypatch):
    _patch_macos(monkeypatch, value=False)


def test_normalize_slash_ru_alias(darwin):
    assert kl.normalize_slash_input(",help") == "/help"
    assert kl.normalize_slash_input("  .clear") == "  /clear"
    assert kl.normalize_slash_input("?copy tool") == "/copy tool"


def test_normalize_slash_unchanged_on_linux(linux):
    assert kl.normalize_slash_input(",help") == ",help"


def test_normalize_does_not_touch_plain_text(darwin):
    assert kl.normalize_slash_input("hello") == "hello"
    assert kl.normalize_slash_input(", world") == ", world"


def test_is_slash_command(darwin):
    assert kl.is_slash_command(",help")
    assert kl.is_slash_command("/help")
    assert not kl.is_slash_command("help")


def test_slash_command_prefix(darwin):
    assert kl.slash_command_prefix(",help args") == "/help"


def test_shortcut_label_macos(darwin):
    assert "⌃" in kl.shortcut_label("ctrl+shift+c")
    assert "⇧" in kl.shortcut_label("ctrl+shift+c")


def test_shortcut_label_linux(linux):
    assert kl.shortcut_label("ctrl+l") == "Ctrl+l"


def test_code_tui_bindings_include_mac_scroll(darwin):
    actions = {b.action for b in kl.code_tui_bindings()}
    assert "scroll_up" in actions
    assert "scroll_down" in actions


def test_main_tui_has_no_copy_binding(darwin, monkeypatch):
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    ids = {b.id for b in kl.code_tui_bindings()}
    assert "copy_output" not in ids
    assert "open_transcript" in ids


def test_viewer_copy_binding_macos(darwin, monkeypatch):
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    copy = next(b for b in kl.transcript_viewer_bindings() if b.id == "viewer_copy")
    assert "super+c" in copy.key
    assert copy.priority is True


def test_apple_terminal_copy_uses_ctrl_c(darwin, monkeypatch):
    monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
    assert kl.is_apple_terminal()
    assert "ctrl+c" in kl.macos_copy_binding_keys()
    assert kl.primary_copy_shortcut_label() == "⌃C"


def test_apple_terminal_startup_hint(darwin, monkeypatch):
    monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
    hint = kl.terminal_copy_hint()
    assert hint is not None
    assert "F2" in hint
    assert "⌃C" in hint


def test_macos_quit_uses_ctrl_q(darwin):
    quit_b = next(b for b in kl.code_tui_bindings() if b.id == "quit")
    assert quit_b.key == "ctrl+q"


def test_code_tui_bindings_no_mac_scroll_on_linux(linux):
    actions = {b.action for b in kl.code_tui_bindings()}
    assert "scroll_up" not in actions


def test_is_macos_matches_platform():
    assert kl.is_macos() == (sys.platform == "darwin")