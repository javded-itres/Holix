"""Tests for LiveTranscriptBuffer."""

from core.presenters.live_buffer import LiveTranscriptBuffer


def test_render_includes_tools_and_answer():
    buf = LiveTranscriptBuffer(profile="p1", mode="react")
    buf.add_tool_start("Read", {"path": "/tmp"})
    buf.add_tool_result("Read", "ok", duration_s=0.5)
    buf.set_answer("Hello **world**")
    buf.mark_done()
    text = buf.render_plain()
    assert "Holix" in text
    assert "Read" in text
    assert "Hello" in text


def test_truncate_answer():
    buf = LiveTranscriptBuffer(max_answer_chars=10)
    buf.set_answer("x" * 100)
    assert len(buf.answer) <= 11


def test_tool_start_clears_partial_answer():
    buf = LiveTranscriptBuffer()
    buf.set_answer("Давайте посмотрю, есть ли активные задачи.")
    buf.add_tool_start("list_subagents", {})
    assert buf.answer == ""


def test_render_shows_error_process_icon():
    buf = LiveTranscriptBuffer(profile="p1", mode="react")
    buf.set_background_process(label="api · pid 1", process_id="proc_1", healthy=False)
    text = buf.render_plain()
    assert "🔴 Process:" in text