"""Recover Qwen/Hermes tool calls leaked as assistant text."""

from __future__ import annotations

from core.graph.action_honesty import ends_turn_on_unexecuted_intent
from core.llm.tool_calls import (
    extract_textual_tool_calls,
    looks_like_leaked_tool_markup,
    strip_tool_call_markup,
)


def test_extract_hermes_json_block() -> None:
    text = (
        "Проверяю активные изменения.\n"
        "<tool_call>\n"
        '{"name": "list_dir", "arguments": {"target_directory": "."}}\n'
        "</tool_call>"
    )
    calls = extract_textual_tool_calls(text)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "list_dir"
    assert '"target_directory"' in calls[0]["function"]["arguments"]
    assert "Проверяю" in strip_tool_call_markup(text)
    assert "tool_call" not in strip_tool_call_markup(text)


def test_extract_qwen_xml_function() -> None:
    text = (
        "<tool_call>\n"
        "<function=read_file>\n"
        "<parameter=path>README.md</parameter>\n"
        "</function>\n"
        "</tool_call>"
    )
    calls = extract_textual_tool_calls(text)
    assert calls[0]["function"]["name"] == "read_file"
    assert "README.md" in calls[0]["function"]["arguments"]


def test_extract_name_then_json() -> None:
    text = '<tool_call>\nlist_directory\n{"path": "."}\n</tool_call>'
    calls = extract_textual_tool_calls(
        text,
        tools=[{"type": "function", "function": {"name": "list_directory"}}],
    )
    assert calls[0]["function"]["name"] == "list_directory"


def test_bare_tool_call_token_is_leak() -> None:
    text = "Проверяю активные изменения и подзадачи в проекте.\n\ntool_call"
    assert looks_like_leaked_tool_markup(text)
    assert extract_textual_tool_calls(text) == []
    assert ends_turn_on_unexecuted_intent(
        text,
        [{"role": "user", "content": "проверь изменения"}],
        user_input="проверь изменения",
    )


def test_known_tools_reject_unknown_name() -> None:
    text = '<tool_call>{"name": "rm_rf", "arguments": {}}</tool_call>'
    tools = [{"type": "function", "function": {"name": "read_file"}}]
    assert extract_textual_tool_calls(text, tools=tools) == []
