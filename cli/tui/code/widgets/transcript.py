"""Transcript that renders Markdown and still exposes the selected text."""

from __future__ import annotations

from rich.segment import Segment
from rich.style import Style
from textual.events import Click, MouseUp
from textual.message import Message
from textual.selection import Selection
from textual.strip import Strip
from textual.widgets import RichLog

from cli.tui.shared.media_links import href_from_line_text, href_from_segments, open_media_href


class CodeTranscript(RichLog):
    """Conversation log. Rich markup is rendered; selection is read from the lines.

    RichLog draws with the line API and never stamps cell offsets, so Textual
    cannot map a mouse drag to text. ``render_line`` adds those offsets, and
    ``get_selection`` returns the plain characters underneath.
    """

    class SelectionReleased(Message):
        """Non-empty selection after the mouse button goes up."""

        bubble = True

        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("id", "transcript")
        kwargs.setdefault("markup", True)
        kwargs.setdefault("wrap", True)
        kwargs.setdefault("highlight", False)
        super().__init__(**kwargs)

    def render_line(self, y: int) -> Strip:
        scroll_x, scroll_y = self.scroll_offset
        doc_y = scroll_y + y
        width = self.scrollable_content_region.width
        line = self._render_line(doc_y, scroll_x, width)
        strip = line.apply_style(self.rich_style)
        selection = self.text_selection
        if selection is not None and (span := selection.get_span(doc_y)) is not None:
            start, end = span
            # The line is already cropped to the viewport, so x is relative to scroll_x.
            start -= scroll_x
            if end >= 0:
                end -= scroll_x
            strip = _paint_span(strip, start, end, self._selection_style())
        # Offsets are what let the mouse drag become a text selection.
        return strip.apply_offsets(scroll_x, doc_y)

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        """Plain text under the highlight. RichLog does not provide this itself."""
        if not self.lines:
            return None
        text = selection.extract("\n".join(strip.text for strip in self.lines))
        text = "\n".join(line.rstrip() for line in text.splitlines())
        if not text.strip():
            return None
        return text, "\n"

    def selection_updated(self, selection: Selection | None) -> None:
        self._line_cache.clear()
        super().selection_updated(selection)
        panel = self.parent
        if panel is not None and hasattr(panel, "selection_updated"):
            panel.selection_updated(selection)

    def _selection_style(self) -> Style:
        # Reverse stays visible even when the theme selection color matches the log.
        fallback = Style(reverse=True)
        try:
            return self.screen.get_component_rich_style("screen--selection") + fallback
        except Exception:
            return fallback

    def on_click(self, event: Click) -> None:
        """Open a generated-media link. RichLog does not surface style.link on clicks."""
        href = ""
        style = getattr(event, "style", None)
        if style is not None and getattr(style, "link", None):
            href = str(style.link)
        if not href:
            href = self._href_at_click(event.y)
        if href and open_media_href(href):
            event.stop()

    def _href_at_click(self, y: int) -> str:
        content_y = int(y) - int(self.content_region.y)
        if content_y < 0:
            return ""
        index = int(self.scroll_offset.y) + content_y
        if index < 0 or index >= len(self.lines):
            return ""
        line = self.lines[index]
        href = href_from_segments(line)
        if href:
            return href
        return href_from_line_text(getattr(line, "text", "") or "")

    def on_mouse_up(self, event: MouseUp) -> None:
        del event
        self.call_later(self._emit_selection)

    def _emit_selection(self) -> None:
        selected = self.text_selection
        if selected is None:
            return
        extracted = self.get_selection(selected)
        if not extracted:
            return
        text = extracted[0].strip()
        if text:
            self.post_message(self.SelectionReleased(text))


def _paint_span(strip: Strip, start: int, end: int, style: Style) -> Strip:
    """Color [start, end) on a strip.

    ``Strip.divide`` drops the tail after the last cut, so a selection painted
    that way never shows. Cut the segments directly instead.
    """
    width = strip.cell_length
    if end < 0 or end > width:
        end = width
    start = max(0, start)
    if start >= end or start >= width:
        return strip
    # The final cut at ``width`` keeps the tail. Without it the last piece is dropped.
    pieces = list(Segment.divide(strip._segments, [start, end, width]))
    if len(pieces) < 3:
        return strip
    widths = (start, end - start, max(0, width - end))
    parts = [Strip(segments, cell_width) for segments, cell_width in zip(pieces[:3], widths)]
    parts[1] = parts[1].apply_style(style)
    return Strip.join(part for part in parts if part.cell_length)
