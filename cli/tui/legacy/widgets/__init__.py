"""Holix TUI widgets."""

from cli.tui.legacy.widgets.chat_log import HolixChatLog
from cli.tui.legacy.widgets.input_area import HolixInputArea
from cli.tui.legacy.widgets.main_content import HolixMainContent
from cli.tui.legacy.widgets.sidebar import HolixSidebar
from cli.tui.legacy.widgets.styles import HOLIX_TUI_CSS

__all__ = [
    "HOLIX_TUI_CSS",
    "HolixChatLog",
    "HolixInputArea",
    "HolixMainContent",
    "HolixSidebar",
]