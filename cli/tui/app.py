"""Holix TUI entry — strict code UI by default, legacy via HOLIX_TUI_LEGACY=1."""

from cli.tui.code.app import HolixCodeApp, run_tui

__all__ = ["HolixCodeApp", "run_tui"]