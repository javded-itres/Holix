"""Footer-style Copy affordance (bright key chip like Escape in Footer)."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.message import Message
from textual.widget import Widget


class CopySelectionBar(Widget):
    """Single-line bar at the bottom of the screen when text is selected."""

    ALLOW_SELECT = False

    COMPONENT_CLASSES = {
        "copy-key",
        "copy-desc",
    }

    DEFAULT_CSS = """
    CopySelectionBar {
        height: 1;
        width: 1fr;
        display: none;
        background: $footer-background;
        padding: 0 1;
    }
    CopySelectionBar.visible {
        display: block;
    }
    CopySelectionBar .copy-key {
        color: $footer-key-foreground;
        background: $footer-key-background;
        text-style: bold;
        padding: 0 1;
    }
    CopySelectionBar .copy-desc {
        color: $footer-description-foreground;
        background: $footer-description-background;
        padding: 0 1 0 0;
    }
    CopySelectionBar:hover {
        background: $block-hover-background;
    }
    """

    class Pressed(Message):
        """User clicked the copy bar."""

        def __init__(self, bar: CopySelectionBar) -> None:
            self.bar = bar
            super().__init__()

        @property
        def control(self) -> CopySelectionBar:
            return self.bar

    def render(self) -> Text:
        key_style = self.get_component_rich_style("copy-key")
        desc_style = self.get_component_rich_style("copy-desc")
        key_pad = self.get_component_styles("copy-key").padding
        desc_pad = self.get_component_styles("copy-desc").padding
        return Text.assemble(
            (
                " " * key_pad.left + "copy" + " " * key_pad.right,
                key_style,
            ),
            (
                " " * desc_pad.left + "Copy selection" + " " * desc_pad.right,
                desc_style,
            ),
        )

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.post_message(self.Pressed(self))