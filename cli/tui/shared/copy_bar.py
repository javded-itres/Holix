"""Copy selection bar visibility helpers."""

from __future__ import annotations

from textual.selection import Selection
from textual.widget import Widget

COPY_BAR_ID = "copy-selection-bar"
VIEWER_COPY_BAR_ID = "viewer-copy-bar"


def _copy_bar_widget(host: Widget, bar_id: str):
    from cli.tui.code.widgets.copy_selection_bar import CopySelectionBar

    return host.query_one(f"#{bar_id}", CopySelectionBar)


def selection_has_text(selection: Selection | None) -> bool:
    if selection is None:
        return False
    start, end = selection
    if start is None or end is None:
        return start is not None or end is not None
    return start != end


def show_copy_bar(host: Widget, bar_id: str = COPY_BAR_ID) -> None:
    try:
        _copy_bar_widget(host, bar_id).add_class("visible")
    except Exception:
        pass


def hide_copy_bar(host: Widget, bar_id: str = COPY_BAR_ID) -> None:
    try:
        _copy_bar_widget(host, bar_id).remove_class("visible")
    except Exception:
        pass