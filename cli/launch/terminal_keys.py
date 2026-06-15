"""Decode terminal keystrokes for relaying to tmux panes."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Literal

KeyEventKind = Literal["char", "keys", "submit", "backspace", "interrupt", "eof"]


@dataclass(frozen=True, slots=True)
class KeyEvent:
    kind: KeyEventKind
    char: str = ""
    keys: tuple[str, ...] = ()


_ESCAPE_SEQUENCES: dict[str, tuple[str, ...]] = {
    "\x1b[A": ("Up",),
    "\x1b[B": ("Down",),
    "\x1b[C": ("Right",),
    "\x1b[D": ("Left",),
    "\x1b[H": ("Home",),
    "\x1b[F": ("End",),
    "\x1b[3~": ("Delete",),
    "\x1bOA": ("Up",),
    "\x1bOB": ("Down",),
    "\x1bOC": ("Right",),
    "\x1bOD": ("Left",),
}


def _read_available_char(timeout: float) -> str | None:
    import select

    if not sys.stdin.isatty():
        return None
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if not ready:
        return None
    char = sys.stdin.read(1)
    return char if char else None


def _read_escape_suffix() -> str:
    import select

    suffix = ""
    for _ in range(3):
        if not select.select([sys.stdin], [], [], 0.02)[0]:
            break
        suffix += sys.stdin.read(1)
    return suffix


def decode_key_event(first_char: str) -> KeyEvent:
    """Turn one stdin byte (plus any following escape bytes) into a relay event."""
    if first_char == "":
        return KeyEvent(kind="eof")

    if first_char in "\r\n":
        return KeyEvent(kind="submit")

    if first_char == "\x03":
        return KeyEvent(kind="interrupt")

    if first_char == "\x04":
        return KeyEvent(kind="eof")

    if first_char in {"\x7f", "\x08"}:
        return KeyEvent(kind="backspace")

    if first_char == "\t":
        return KeyEvent(kind="keys", keys=("Tab",))

    if first_char == "\x1b":
        suffix = _read_escape_suffix()
        mapped = _ESCAPE_SEQUENCES.get(first_char + suffix)
        if mapped:
            return KeyEvent(kind="keys", keys=mapped)
        if not suffix:
            return KeyEvent(kind="keys", keys=("Escape",))
        return KeyEvent(kind="char", char=first_char)

    if first_char.isprintable():
        return KeyEvent(kind="char", char=first_char)

    return KeyEvent(kind="char", char=first_char)


def read_key_event(timeout: float) -> KeyEvent | None:
    """Read a single key event or return None on timeout."""
    first = _read_available_char(timeout)
    if first is None:
        return None
    return decode_key_event(first)