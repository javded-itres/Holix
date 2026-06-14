"""Tests for Telegram HTML helpers."""

from core.presenters.live_buffer import LiveTranscriptBuffer
from integrations.telegram.markdown import (
    escape_html,
    markdown_to_telegram_html,
    plain_to_telegram_html,
    split_telegram_html,
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


def test_split_telegram_html_multiple_chunks() -> None:
    html = "<p>" + "word " * 2500 + "</p>"
    chunks = split_telegram_html(html, max_len=500)
    assert len(chunks) >= 2
    assert all(len(c) <= 500 for c in chunks)


def test_compact_tools_show_header_only() -> None:
    buf = LiveTranscriptBuffer(profile="default", mode="react", compact_tools=True)
    buf.add_tool_start("read_file", {"path": "/very/long/path/file.py"})
    buf.add_tool_result("read_file", "x" * 500, duration_s=0.5)
    html = buffer_to_telegram_html(buf)
    assert "read_file" in html
    assert "/very/long/path" not in html
    assert "<code>" not in html


def test_done_with_tools_hides_tools_keeps_rendered_answer() -> None:
    buf = LiveTranscriptBuffer(profile="default", mode="react")
    buf.add_tool_start("read", {"path": "a.py"})
    buf.set_answer("**Done**")
    buf.mark_done()
    html = buffer_to_telegram_html(buf)
    assert "<b>Done</b>" in html
    assert "read" not in html


def test_telegram_done_posts_answer_separately_not_in_live_card() -> None:
    buf = LiveTranscriptBuffer(profile="default", mode="react")
    buf.publish_answer_separately = True
    buf.result_posted_separately = True
    buf.set_answer("**Secret final**")
    buf.mark_done()
    html = buffer_to_telegram_html(buf)
    assert "<b>Secret final</b>" not in html
    from core.i18n.live_ui import live_answer_sent_label

    assert live_answer_sent_label("default") in html