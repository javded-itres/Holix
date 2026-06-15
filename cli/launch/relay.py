"""Interactive relay between Holix terminal and an external CLI tmux pane."""

from __future__ import annotations

import sys
import termios
import time
import tty
from collections.abc import Callable
from contextlib import contextmanager

from rich.panel import Panel

from cli.launch.terminal_keys import read_key_event
from cli.services.tmux_launcher import capture_pane, send_keys, send_text
from cli.utils.rich_console import console, print_info

_RELAY_HELP = (
    "Arrow keys, Tab, Esc go straight to the CLI (for choice menus).\n"
    "Type text + Enter for prompts. 1-9 with empty input picks a numbered option.\n"
    "Ctrl+C quits relay."
)


def pane_ready_to_emit(
    *,
    pending: str | None,
    last_printed: str,
    stable_since: float | None,
    now: float,
    stable_for: float = 0.35,
) -> bool:
    """Return True when pane text stopped changing long enough to display."""
    if not pending or pending == last_printed:
        return False
    if stable_since is None:
        return False
    return now - stable_since >= stable_for


@contextmanager
def _cbreak_stdin():
    if not sys.stdin.isatty():
        yield
        return
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _emit_pane(pane: str, *, last_printed: str) -> str:
    text = pane or "(empty)"
    console.print(Panel(text, title="CLI", border_style="green"))
    return pane


def _handle_quick_choice(
    tmux_session: str,
    *,
    window_index: int,
    digit: str,
    on_user_send: Callable[[str], None] | None,
) -> None:
    send_keys(tmux_session, [digit, "Enter"], window_index=window_index)
    if on_user_send is not None:
        on_user_send(f"[{digit}]")


def run_cli_relay(
    tmux_session: str,
    window_index: int = 0,
    *,
    poll_interval: float = 0.15,
    stable_for: float = 0.35,
    capture_lines: int = 120,
    on_user_send: Callable[[str], None] | None = None,
) -> None:
    """Poll tmux pane and forward prompts/keys to the external CLI."""
    console.print(
        Panel.fit(
            f"[bold]Relay → {tmux_session}:{window_index}[/bold]\n{_RELAY_HELP}",
            border_style="cyan",
        )
    )

    last_printed = ""
    pending: str | None = None
    stable_since: float | None = None
    input_buffer = ""
    prompt_shown = False

    try:
        with _cbreak_stdin():
            while True:
                now = time.monotonic()
                pane = capture_pane(
                    tmux_session,
                    window_index=window_index,
                    lines=capture_lines,
                )

                if pane != pending:
                    pending = pane
                    stable_since = now
                elif pane_ready_to_emit(
                    pending=pending,
                    last_printed=last_printed,
                    stable_since=stable_since,
                    now=now,
                    stable_for=stable_for,
                ):
                    last_printed = _emit_pane(pending or "", last_printed=last_printed)
                    prompt_shown = False

                if not prompt_shown:
                    console.print("[bold cyan]holix[/bold cyan] ", end="")
                    if input_buffer:
                        sys.stdout.write(input_buffer)
                    sys.stdout.flush()
                    prompt_shown = True

                event = read_key_event(poll_interval)
                if event is None:
                    continue

                if event.kind == "interrupt":
                    raise KeyboardInterrupt
                if event.kind == "eof":
                    break

                if event.kind == "keys":
                    input_buffer = ""
                    prompt_shown = False
                    send_keys(tmux_session, list(event.keys), window_index=window_index)
                    if on_user_send is not None:
                        on_user_send(" ".join(event.keys))
                    pending = None
                    stable_since = None
                    last_printed = ""
                    continue

                if event.kind == "backspace":
                    if input_buffer:
                        input_buffer = input_buffer[:-1]
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                    continue

                if event.kind == "submit":
                    prompt_shown = False
                    console.print()
                    text = input_buffer.strip()
                    input_buffer = ""
                    if not text:
                        if pending and pending != last_printed:
                            last_printed = _emit_pane(
                                pending or "",
                                last_printed=last_printed,
                            )
                        continue
                    send_text(tmux_session, text, window_index=window_index)
                    if on_user_send is not None:
                        on_user_send(text)
                    pending = None
                    stable_since = None
                    last_printed = ""
                    continue

                if event.kind == "char" and event.char:
                    if (
                        not input_buffer
                        and event.char.isdigit()
                        and event.char != "0"
                    ):
                        prompt_shown = False
                        console.print()
                        _handle_quick_choice(
                            tmux_session,
                            window_index=window_index,
                            digit=event.char,
                            on_user_send=on_user_send,
                        )
                        pending = None
                        stable_since = None
                        last_printed = ""
                        continue

                    input_buffer += event.char
                    sys.stdout.write(event.char)
                    sys.stdout.flush()

    except KeyboardInterrupt:
        console.print()
    print_info("Relay ended.")