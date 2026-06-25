"""LLM API message sanitization (issue #41)."""

from __future__ import annotations

from core.llm.api_messages import prepare_conversation_for_llm
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