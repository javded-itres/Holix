"""Platform guards for external CLI + tmux launch."""

from __future__ import annotations

import shutil

from core.platform_compat import IS_LINUX, IS_MACOS, IS_POSIX


class LaunchPlatformError(RuntimeError):
    """Raised when launch is requested on an unsupported platform."""


def launch_supported() -> bool:
    return IS_POSIX and (IS_LINUX or IS_MACOS)


def tmux_available() -> bool:
    return bool(shutil.which("tmux"))


def ensure_launch_platform() -> None:
    if not launch_supported():
        raise LaunchPlatformError(
            "holix launch is available only on Linux and macOS. "
            "Use holix tui or holix gateway on other platforms."
        )
    if not tmux_available():
        raise LaunchPlatformError(
            "tmux is not installed. Install it (brew install tmux / apt install tmux) "
            "and run: holix launch setup"
        )