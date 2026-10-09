"""Welcome screen picks the saved TUI session when it still has messages."""

from cli.tui.modals.welcome import pick_last_tui_session


def test_prefers_saved_tui_session() -> None:
    rows = [
        {"conversation_id": "tui_default_9", "message_count": 4, "last_timestamp": "2"},
        {"conversation_id": "tui_default", "message_count": 12, "last_timestamp": "1"},
        {"conversation_id": "tg_admin_1", "message_count": 99, "last_timestamp": "3"},
    ]
    picked = pick_last_tui_session(rows, "tui_default")
    assert picked is not None
    assert picked["conversation_id"] == "tui_default"


def test_newest_tui_session_when_saved_is_empty() -> None:
    rows = [
        {"conversation_id": "tui_default_9", "message_count": 3, "last_timestamp": "2"},
        {"conversation_id": "cron_internal", "message_count": 8, "last_timestamp": "9"},
    ]
    picked = pick_last_tui_session(rows, "tui_default")
    assert picked is not None
    assert picked["conversation_id"] == "tui_default_9"


def test_no_session_when_nothing_stored() -> None:
    assert pick_last_tui_session([], "tui_default") is None


def test_skips_a_conversation_another_window_holds() -> None:
    rows = [
        {"conversation_id": "tui_default_9", "message_count": 4, "last_timestamp": "2"},
        {"conversation_id": "tui_default_3", "message_count": 2, "last_timestamp": "1"},
    ]
    picked = pick_last_tui_session(
        rows,
        "tui_default_9",
        busy=lambda cid: cid == "tui_default_9",
    )
    assert picked is not None
    assert picked["conversation_id"] == "tui_default_3"
