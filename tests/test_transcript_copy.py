"""Transcript renders Rich markup and can still return the selected text."""

from cli.tui.code.widgets.transcript import CodeTranscript, _paint_span
from cli.tui.shared.transcript_store import plain_from_rich_write
from rich.markdown import Markdown
from rich.segment import Segment
from rich.style import Style
from textual.geometry import Offset
from textual.selection import Selection
from textual.strip import Strip


def test_transcript_renders_with_rich_log() -> None:
    assert CodeTranscript.__mro__[1].__name__ == "RichLog"


def test_selection_reads_rendered_lines() -> None:
    log = CodeTranscript()
    log.lines.extend(
        [
            Strip([Segment("Привет, "), Segment("мир")]),
            Strip([Segment("вторая строка")]),
        ]
    )
    selected = Selection.from_offsets(Offset(0, 0), Offset(4, 1))
    extracted = log.get_selection(selected)
    assert extracted is not None
    text, ending = extracted
    assert "Привет, мир" in text
    assert text.splitlines()[1].startswith("втор")
    assert ending == "\n"


def test_paint_span_styles_the_middle() -> None:
    strip = Strip([Segment("abcdef")])
    painted = _paint_span(strip, 2, 5, Style(reverse=True))
    assert painted.text == "abcdef"
    selected = next(segment for segment in painted._segments if segment.text == "cde")
    assert selected.style is not None and selected.style.reverse is True


def test_plain_from_markup_is_copyable() -> None:
    plain, _md = plain_from_rich_write("[bold]❯[/bold] проверь ключ")
    assert "проверь ключ" in plain
    assert "[" not in plain


def test_plain_from_markdown_renderable() -> None:
    plain, _md = plain_from_rich_write(Markdown("**готово**"))
    assert "готово" in plain
