"""MAX HTML formatting helpers."""

from __future__ import annotations

from core.presenters.live_buffer import LiveTranscriptBuffer
from integrations.max.markdown import (
    escape_html,
    looks_like_markdown,
    markdown_to_max_html,
    plain_to_max_html,
    prepare_max_html,
    prepare_max_markdown,
    split_max_html,
    split_max_text,
    truncate_max_html,
    truncate_max_text,
)
from integrations.max.render import buffer_to_max_html


def test_truncate_max_text() -> None:
    assert truncate_max_text("abc", limit=10) == "abc"
    assert truncate_max_text("x" * 20, limit=10).endswith("…")


def test_split_max_text_chunks_long_message() -> None:
    text = "line\n" * 2000
    chunks = split_max_text(text, limit=500)
    assert len(chunks) > 1
    assert all(len(c) <= 500 for c in chunks)


def test_prepare_max_markdown_headers() -> None:
    raw = "### Выводы\n\nТекст **важный**."
    out = prepare_max_markdown(raw)
    assert out.startswith("# Выводы")
    assert "**важный**" in out


def test_prepare_max_markdown_code_fence() -> None:
    raw = "Пример:\n```python\nprint('hi')\nx = 1\n```"
    out = prepare_max_markdown(raw)
    assert "**Код:**" in out
    assert "> print('hi')" in out
    assert "```" not in out


def test_prepare_max_markdown_single_line_code() -> None:
    raw = "Команда `ls -la` работает."
    assert prepare_max_markdown(raw) == raw


def test_looks_like_markdown() -> None:
    assert looks_like_markdown("**Жирный** текст")
    assert looks_like_markdown("- пункт списка")
    assert not looks_like_markdown("Простой ответ без разметки")
    assert not looks_like_markdown("⏳ Holix обрабатывает запрос…")


def test_escape_html() -> None:
    assert "&lt;" in escape_html("<tag>")


def test_markdown_bold_renders_html() -> None:
    out = markdown_to_max_html("**Hello** world")
    assert "<b>Hello</b>" in out
    assert "**Hello**" not in out
    assert "<pre>" not in out


def test_markdown_code_block_uses_pre() -> None:
    out = markdown_to_max_html("Text\n```python\nx = 1\n```\nDone")
    assert "<pre>" in out
    assert out.count("<pre>") == 1


def test_plain_to_max_html_no_shell_wrap() -> None:
    out = plain_to_max_html("Answer with **bold**")
    assert "<pre>" not in out
    assert "<b>bold</b>" in out


def test_prepare_max_html_final_answer() -> None:
    out = prepare_max_html("## Result\n\n**OK** — done.\n\n`pip install helix`")
    assert "<b>OK</b>" in out
    assert "**OK**" not in out
    assert "<code>pip install helix</code>" in out


def test_buffer_final_answer_renders_html() -> None:
    buf = LiveTranscriptBuffer(profile="default", mode="react")
    buf.set_answer("## Result\n\n**OK** — done.\n\n`pip install helix`")
    buf.mark_done()
    html = buffer_to_max_html(buf)
    assert "<b>OK</b>" in html
    assert "**OK**" not in html
    assert "🤖 default" in html


def test_truncate_max_html_closes_tags() -> None:
    html = "<b>" + "x" * 200 + "</b><i>tail"
    out = truncate_max_html(html, 50)
    assert len(out) <= 50
    assert out.count("<b>") == out.count("</b>")


def test_split_max_html_multiple_chunks() -> None:
    html = "<b>" + "word " * 2500 + "</b>"
    chunks = split_max_html(html, max_len=500)
    assert len(chunks) >= 2
    assert all(len(c) <= 500 for c in chunks)