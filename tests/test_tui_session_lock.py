"""Two TUI windows must not attach to one live conversation."""

from __future__ import annotations

import os

from cli.tui.session_lock import (
    claim_conversation,
    conversation_busy,
    release_conversation,
    window_id,
    window_state_path,
)


def _dead_pid() -> int:
    for pid in range(1_000_000, 1_000_400):
        try:
            os.kill(pid, 0)
        except PermissionError:
            continue
        except OSError:
            # Unix: the pid is unused. Windows: signal 0 on a missing pid
            # is WinError 87, not ProcessLookupError.
            return pid
    raise AssertionError("no unused pid")


def test_window_state_is_per_process(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    monkeypatch.delenv("HOLIX_TUI_WINDOW", raising=False)
    assert window_id() == str(os.getpid())
    assert window_state_path() == tmp_path / "tui-sessions" / f"{os.getpid()}.json"
    monkeypatch.setenv("HOLIX_TUI_WINDOW", "../other window")
    assert "/" not in window_id()
    assert window_id() == "___other_window"


def test_live_owner_blocks_a_second_claim(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    assert claim_conversation("tui_default_1") is True
    assert conversation_busy("tui_default_1") is False
    lock = tmp_path / "tui-sessions" / "locks" / "tui_default_1.lock"
    lock.write_text(str(os.getppid()), encoding="utf-8")
    assert conversation_busy("tui_default_1") is True
    assert claim_conversation("tui_default_1") is False
    assert lock.read_text(encoding="utf-8") == str(os.getppid())


def test_dead_owner_can_be_replaced_and_release_clears_only_us(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOLIX_HOME", str(tmp_path))
    lock = tmp_path / "tui-sessions" / "locks" / "tui_default_2.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(str(_dead_pid()), encoding="utf-8")
    assert conversation_busy("tui_default_2") is False
    assert claim_conversation("tui_default_2") is True
    assert lock.read_text(encoding="utf-8") == str(os.getpid())
    release_conversation("tui_default_2")
    assert lock.read_text(encoding="utf-8") == ""
    lock.write_text(str(os.getppid()), encoding="utf-8")
    release_conversation("tui_default_2")
    assert lock.read_text(encoding="utf-8") == str(os.getppid())


def test_empty_conversation_is_not_claimable() -> None:
    assert claim_conversation("  ") is False
    assert conversation_busy("") is False
