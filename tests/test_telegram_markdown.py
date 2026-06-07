"""Tests for Telegram HTML helpers."""

from core.presenters.live_buffer import LiveTranscriptBuffer
from integrations.telegram.markdown import (
    escape_html,
    markdown_to_telegram_html,
    plain_to_telegram_html,
    truncate_telegram_html,
)
from integrations.telegram.render import buffer_to_telegram_html


def test_escape_html() -> None:
    assert "&lt;" in escape_html("<tag>")


def test_markdown_bold_not_wrapped_in_pre() -> None:
    out = markdown_to_telegram_html("**Hello** world")
    assert "<b>Hello</b>" in out
    assert "<pre>" not in out


def test_markdown_code_block_uses_pre_only_for_code() -> None:
    out = markdown_to_telegram_html("Text\n```python\nx = 1\n```\nDone")
    assert "<pre>" in out
    assert out.index("<pre>") > out.index("Text") or "Done" in out
    assert out.count("<pre>") == 1


def test_plain_to_telegram_html_no_shell_wrap() -> None:
    out = plain_to_telegram_html("Answer with **bold**")
    assert "<pre>" not in out
    assert "<b>bold</b>" in out


def test_buffer_final_answer_renders_markdown() -> None:
    buf = LiveTranscriptBuffer(profile="default", mode="react")
    buf.set_answer("## Result\n\n**OK** — done.\n\n`pip install helix`")
    buf.mark_done()
    html = buffer_to_telegram_html(buf)
    assert "<pre>" not in html or "pip install helix" in html
    assert "<b>OK</b>" in html
    assert "🤖 default" in html


def test_truncate_telegram_html_closes_tags() -> None:
    html = "<b>" + "x" * 200 + "</b><i>tail"
    out = truncate_telegram_html(html, 50)
    assert len(out) <= 50
    assert out.count("<b>") == out.count("</b>")
    assert "**" not in out


def test_long_final_answer_stays_html_not_raw_markdown() -> None:
    buf = LiveTranscriptBuffer(profile="p", mode="react")
    buf.set_answer("**Intro** " + "word " * 900 + "\n\n## End\n\n`ok`")
    buf.mark_done()
    html = buffer_to_telegram_html(buf)
    assert "<b>Intro</b>" in html
    assert "**Intro**" not in html
    assert len(html) <= 4090


def test_done_with_tools_hides_tools_keeps_rendered_answer() -> None:
    buf = LiveTranscriptBuffer(profile="default", mode="react")
    buf.add_tool_start("read", {"path": "a.py"})
    buf.set_answer("**Done**")
    buf.mark_done()
    html = buffer_to_telegram_html(buf)
    assert "<b>Done</b>" in html
    assert "read" not in html