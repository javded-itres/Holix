"""Cross-platform helpers."""

from __future__ import annotations

import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core import platform_compat as pc


def test_resolve_holix_home_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custom = tmp_path / "custom-helix"
    monkeypatch.setenv("HOLIX_HOME", str(custom))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert pc.resolve_holix_home() == custom.resolve()


def test_resolve_holix_home_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOLIX_HOME", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(pc, "IS_WINDOWS", False)
    assert pc.resolve_holix_home() == (tmp_path / "xdg" / "holix").resolve()


def test_resolve_holix_home_windows_localappdata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOLIX_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    monkeypatch.setattr(pc, "IS_WINDOWS", True)
    assert pc.resolve_holix_home() == (tmp_path / "AppData" / "Local" / "Holix").resolve()


def test_port_check_hint_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pc, "IS_WINDOWS", True)
    monkeypatch.setattr(pc, "IS_MACOS", False)
    hint = pc.port_check_hint(8000)
    assert "netstat" in hint
    assert "8000" in hint


@patch.object(pc, "is_process_alive", return_value=False)
def test_terminate_process_noop_when_dead(_alive: MagicMock) -> None:
    pc.terminate_process(99999)


@patch.object(pc, "_psutil_terminate_tree", return_value=False)
@patch.object(pc.os, "killpg", create=True)
@patch.object(pc.os, "getpgid", create=True, side_effect=OSError("no pgid"))
@patch.object(pc, "is_process_alive", side_effect=[True, False])
@patch.object(pc, "_kill_signal")
def test_terminate_process_sigterm_fallback(
    mock_kill: MagicMock,
    _alive: MagicMock,
    _pgid: MagicMock,
    _killpg: MagicMock,
    _psutil: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pc, "IS_WINDOWS", False)
    monkeypatch.setattr(pc, "IS_POSIX", True)
    pc.terminate_process(42, grace=0.1)
    mock_kill.assert_called_with(42, signal.SIGTERM)


def test_process_subagents_not_supported_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pc, "IS_WINDOWS", True)
    assert pc.process_subagents_supported() is False


def test_prefer_async_subagents_when_piped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pc.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(pc.sys.stdout, "isatty", lambda: True)
    assert pc.prefer_async_subagents() is True


def test_prefer_async_subagents_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLIX_SUBAGENT_PROCESS", "1")
    monkeypatch.setattr(pc.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(pc.sys.stdout, "isatty", lambda: False)
    assert pc.prefer_async_subagents() is False


def test_ensure_multiprocessing_support_calls_freeze_support() -> None:
    with patch("multiprocessing.freeze_support") as mock_fs:
        pc.ensure_multiprocessing_support()
    mock_fs.assert_called_once()


@patch.object(pc, "_psutil_terminate_tree", return_value=True)
@patch.object(pc, "is_process_alive", side_effect=[True, False])
def test_terminate_process_uses_psutil_when_available(
    _alive: MagicMock, mock_psutil: MagicMock
) -> None:
    pc.terminate_process(100, grace=0.1)
    mock_psutil.assert_any_call(100, force=False)


def test_slugify_skill_name() -> None:
    from core.hub.normalize import slugify_skill_name

    assert slugify_skill_name("test_skill") == "test-skill"
    assert slugify_skill_name("My Skill!") == "my-skill"


def test_subprocess_shell_kwargs_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pc, "IS_WINDOWS", True)
    monkeypatch.setattr(pc, "_CREATE_NO_WINDOW", 0x08000000)
    kwargs = pc.subprocess_shell_kwargs()
    assert kwargs.get("creationflags") == 0x08000000


def test_subprocess_shell_kwargs_unix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pc, "IS_WINDOWS", False)
    assert pc.subprocess_shell_kwargs() == {}


def test_psutil_available_false_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def _import(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("no psutil")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _import)
    assert pc.psutil_available() is False