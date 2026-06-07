"""System clipboard helper."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from cli.tui.shared.clipboard import copy_text_best_effort, copy_to_system_clipboard


def test_copy_to_system_clipboard_empty() -> None:
    assert copy_to_system_clipboard("") is False


@patch("cli.tui.shared.clipboard.subprocess.run")
def test_copy_to_system_clipboard_macos(mock_run: MagicMock) -> None:
    with patch("cli.tui.shared.clipboard.sys.platform", "darwin"):
        assert copy_to_system_clipboard("hello") is True
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0] == ["pbcopy"]


@patch("cli.tui.shared.clipboard.copy_to_system_clipboard", return_value=True)
def test_copy_text_best_effort_prefers_system(mock_sys: MagicMock) -> None:
    app = MagicMock()
    assert copy_text_best_effort(app, "x") is True
    app.copy_to_clipboard.assert_not_called()


@patch("cli.tui.shared.clipboard.copy_to_system_clipboard", return_value=False)
def test_copy_text_best_effort_falls_back_to_textual(mock_sys: MagicMock) -> None:
    app = MagicMock()
    assert copy_text_best_effort(app, "x") is True
    app.copy_to_clipboard.assert_called_once_with("x")


@patch("cli.tui.shared.clipboard.subprocess.run")
@patch("cli.tui.shared.clipboard.shutil.which", return_value="clip.exe")
def test_copy_to_system_clipboard_windows(mock_which: MagicMock, mock_run: MagicMock) -> None:
    with patch("cli.tui.shared.clipboard.IS_WINDOWS", True):
        with patch("cli.tui.shared.clipboard.sys.platform", "win32"):
            assert copy_to_system_clipboard("hello") is True
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0] == ["clip.exe"]