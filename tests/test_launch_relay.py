"""holix launch relay tests."""

from __future__ import annotations

from cli.launch.relay import pane_ready_to_emit
from cli.launch.terminal_keys import decode_key_event


def test_decode_arrow_keys() -> None:
    from cli.launch import terminal_keys as tk

    original = tk._read_escape_suffix
    try:
        tk._read_escape_suffix = lambda: "[C"
        assert decode_key_event("\x1b").keys == ("Right",)
    finally:
        tk._read_escape_suffix = original


def test_decode_key_event_variants() -> None:
    assert decode_key_event("\r").kind == "submit"
    assert decode_key_event("\n").kind == "submit"
    assert decode_key_event("\x03").kind == "interrupt"
    assert decode_key_event("\x7f").kind == "backspace"
    assert decode_key_event("\t").keys == ("Tab",)
    assert decode_key_event("a").char == "a"


def test_decode_escape_sequences_direct() -> None:
    from cli.launch import terminal_keys as tk

    original = tk._read_escape_suffix
    try:
        tk._read_escape_suffix = lambda: "[A"
        assert decode_key_event("\x1b").keys == ("Up",)
        tk._read_escape_suffix = lambda: "[B"
        assert decode_key_event("\x1b").keys == ("Down",)
        tk._read_escape_suffix = lambda: ""
        assert decode_key_event("\x1b").keys == ("Escape",)
    finally:
        tk._read_escape_suffix = original


def test_pane_ready_to_emit_when_stable() -> None:
    assert pane_ready_to_emit(
        pending="❯ 1. Yes\n  2. No",
        last_printed="",
        stable_since=0.0,
        now=0.4,
    )
    assert not pane_ready_to_emit(
        pending="thinking",
        last_printed="",
        stable_since=0.3,
        now=0.5,
    )