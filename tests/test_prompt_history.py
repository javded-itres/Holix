"""Prompt history store for TUI input recall."""

from __future__ import annotations

from cli.tui.shared.prompt_history import PromptHistoryStore


def test_record_keeps_newest_first_and_dedupes():
    store = PromptHistoryStore(limit=5)
    store.record("first")
    store.record("second")
    store.record("first")
    assert store.recent() == ["first", "second"]


def test_record_respects_limit():
    store = PromptHistoryStore(limit=5)
    for i in range(7):
        store.record(f"msg-{i}")
    assert store.recent() == [
        "msg-6",
        "msg-5",
        "msg-4",
        "msg-3",
        "msg-2",
    ]


def test_load_and_dump_roundtrip():
    store = PromptHistoryStore(limit=5)
    store.load(["  a  ", "b", "", "c", "d", "e", "f"])
    assert store.dump() == ["a", "b", "c", "d", "e"]