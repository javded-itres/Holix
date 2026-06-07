"""Strict code-style TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["HelixCodeApp", "run_tui"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from cli.tui.code.app import HelixCodeApp, run_tui

        return {"HelixCodeApp": HelixCodeApp, "run_tui": run_tui}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:
    from cli.tui.code.app import HelixCodeApp, run_tui