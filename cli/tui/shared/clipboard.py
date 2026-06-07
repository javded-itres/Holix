"""System clipboard helpers (macOS pbcopy, Linux wl-copy/xclip, Windows clip)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any

from core.platform_compat import IS_WINDOWS


def copy_to_system_clipboard(text: str) -> bool:
    """Copy UTF-8 text to the OS clipboard. Returns True on success."""
    if not text:
        return False

    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["pbcopy"],
                input=text.encode("utf-8"),
                check=True,
                timeout=5,
            )
            return True

        if IS_WINDOWS:
            if clip := shutil.which("clip"):
                subprocess.run(
                    [clip],
                    input=text.encode("utf-16le"),
                    check=True,
                    timeout=5,
                )
                return True
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "[Console]::InputEncoding = [Text.UTF8Encoding]::UTF8; "
                    "$input | Set-Clipboard",
                ],
                input=text.encode("utf-8"),
                check=True,
                timeout=10,
            )
            return True

        if (wl_copy := shutil.which("wl-copy")) is not None:
            subprocess.run(
                [wl_copy],
                input=text.encode("utf-8"),
                check=True,
                timeout=5,
            )
            return True

        if (xclip := shutil.which("xclip")) is not None:
            subprocess.run(
                [xclip, "-selection", "clipboard"],
                input=text.encode("utf-8"),
                check=True,
                timeout=5,
            )
            return True

        if (xsel := shutil.which("xsel")) is not None:
            subprocess.run(
                [xsel, "--clipboard", "--input"],
                input=text.encode("utf-8"),
                check=True,
                timeout=5,
            )
            return True
    except (OSError, subprocess.SubprocessError):
        return False

    return False


def copy_text_best_effort(app: Any, text: str) -> bool:
    """System clipboard first, then Textual OSC 52 fallback."""
    if copy_to_system_clipboard(text):
        return True
    try:
        app.copy_to_clipboard(text)
        return True
    except Exception:
        return False