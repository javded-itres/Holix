"""Helix TUI entry — strict code UI by default, legacy via HELIX_TUI_LEGACY=1."""

from cli.tui.code.app import HelixCodeApp, run_tui

__all__ = ["HelixCodeApp", "run_tui"]