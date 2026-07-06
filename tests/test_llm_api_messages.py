"""LLM API message sanitization (issue #41)."""

from __future__ import annotations

from core.llm.api_messages import (
    finalize_api_messages,
    prepare_conversation_for_llm,
    repair_api_message_sequence,
)
from core.profile.soul import build_soul_message


def test_prepare_strips_soul_metadata_and_extra_system_role() -> None:
    soul = build_soul_message("default")
    messages = [
        soul,
        {"role": "system", "content": "Context compressed. Summary…"},
        {"role": "user", "content": "hello"},
    ]

    prepared = prepare_conversation_for_llm(messages)

    assert len(prepared) == 2
    assert prepared[0]["role"] == "user"
    assert prepared[0]["content"].startswith("[Context note]")
    assert prepared[1] == {"role": "user", "content": "hello"}
    assert "metadata" not in prepared[0]
    assert all(msg.get("role") != "system" for msg in prepared)


def test_prepare_keeps_tool_turns_without_metadata() -> None:
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
            "metadata": {"step": 1},
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "ok",
            "metadata": {"tool_name": "read_file"},
        },
    ]

    prepared = prepare_conversation_for_llm(messages)

    assert prepared == [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": messages[0]["tool_calls"],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
    ]


def test_prepare_defers_system_note_during_tool_turn() -> None:
    """Regression: system→user in the middle of tool_calls broke provider ordering."""
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "web_search", "arguments": "{}"},
                }
            ],
        },
        {"role": "system", "content": "Context compressed. Summary…"},
        {"role": "tool", "tool_call_id": "call_1", "content": "hits"},
        {"role": "user", "content": "continue"},
    ]

    prepared = prepare_conversation_for_llm(messages)

    assert prepared[0]["role"] == "assistant"
    assert prepared[1] == {"role": "tool", "tool_call_id": "call_1", "content": "hits"}
    assert prepared[2]["role"] == "user"
    assert prepared[2]["content"].startswith("[Context note]")
    assert "continue" in prepared[2]["content"]
    assert not any(i > 0 and prepared[i]["role"] == "tool" and prepared[i - 1]["role"] == "user" for i in range(len(prepared)))


def test_repair_tool_after_user_from_truncation() -> None:
    messages = [
        {"role": "user", "content": "latest question"},
        {"role": "tool", "tool_call_id": "call_1", "content": "orphan after truncate"},
    ]

    repaired = repair_api_message_sequence(messages)

    assert repaired == [
        {
            "role": "user",
            "content": "latest question\n\n[Tool result]\norphan after truncate",
        }
    ]


def test_finalize_drops_leading_orphan_tools() -> None:
    messages = [
        {"role": "tool", "tool_call_id": "call_1", "content": "dropped"},
        {"role": "user", "content": "hi"},
    ]

    assert finalize_api_messages(messages) == [{"role": "user", "content": "hi"}]