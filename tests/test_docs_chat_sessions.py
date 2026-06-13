"""Tests for docs chat per-visitor session storage."""

from __future__ import annotations

import pytest
from core.docs_chat.sessions import (
    append_exchange,
    clear_session,
    history_for_llm,
    load_session,
    save_session,
    validate_client_id,
)


@pytest.fixture
def sessions_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    chat_dir = tmp_path / "data" / "docs_chat"
    chat_dir.mkdir(parents=True)
    monkeypatch.setattr("core.docs_chat.sessions._sessions_dir", lambda: chat_dir)
    return chat_dir


def test_validate_client_id_accepts_uuid() -> None:
    assert validate_client_id("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def test_validate_client_id_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        validate_client_id("../etc/passwd")


def test_append_and_load_session(sessions_dir) -> None:
    cid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    append_exchange(
        cid,
        user_message="How to install?",
        assistant_message="Use pipx install Holix",
        pages=[{"slug": "installation", "title": "Installation"}],
    )
    session = load_session(cid)
    assert len(session["messages"]) == 2
    assert session["messages"][0]["role"] == "user"
    assert session["messages"][1]["pages"][0]["slug"] == "installation"


def test_history_for_llm_strips_metadata(sessions_dir) -> None:
    cid = "b2c3d4e5-f6a7-8901-bcde-f12345678901"
    save_session(
        cid,
        [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello", "pages": [{"slug": "readme", "title": "Readme"}]},
        ],
    )
    history = history_for_llm(load_session(cid)["messages"])
    assert history == [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]


def test_clear_session(sessions_dir) -> None:
    cid = "c3d4e5f6-a7b8-9012-cdef-123456789012"
    append_exchange(cid, user_message="Q", assistant_message="A")
    clear_session(cid)
    assert load_session(cid)["messages"] == []