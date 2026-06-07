"""Tests for plain-text transcript store (TUI copy/export)."""

from __future__ import annotations

from cli.tui.shared.transcript_store import (
    TranscriptStore,
    plain_from_rich_write,
    strip_rich_markup,
)


def test_strip_rich_markup():
    assert strip_rich_markup("[bold]hi[/bold] there") == "hi there"


def test_plain_from_rich_string():
    plain, md = plain_from_rich_write("[dim]ready[/dim]")
    assert plain == "ready"
    assert md is None


def test_append_and_format_all():
    store = TranscriptStore()
    store.append("user", "hello")
    store.append("assistant", "world", markdown="**world**")
    store.append("tool", "output", title="Read")
    text = store.format_all()
    assert "❯ hello" in text
    assert "world" in text
    assert "⎿ Read" in text
    assert "output" in text


def test_stream_flush():
    store = TranscriptStore()
    store.append_stream_delta("hel")
    store.append_stream_delta("lo")
    store.flush_stream_to_assistant(markdown="**hello**")
    assert store.last_assistant() == "**hello**"
    assert not store.has_stream_buffer()


def test_last_assistant_prefers_markdown():
    store = TranscriptStore()
    store.append("assistant", "plain", markdown="# title")
    assert store.last_assistant() == "# title"


def test_last_tool_and_user():
    store = TranscriptStore()
    store.append("user", "u1")
    store.append("tool", "t1", title="Shell")
    store.append("user", "u2")
    assert store.last_user() == "u2"
    assert store.last_tool() == "t1"


def test_clear():
    store = TranscriptStore()
    store.append("user", "x")
    store.append_stream_delta("y")
    store.clear()
    assert store.entries == []
    assert not store.has_stream_buffer()