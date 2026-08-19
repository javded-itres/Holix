"""Recover Qwen/Hermes tool calls leaked as assistant text."""

from __future__ import annotations

import json

from core.graph.action_honesty import ends_turn_on_unexecuted_intent
from core.llm.completion import (
    first_choice_message,
    is_blank_final_text,
    is_empty_llm_response,
)
from core.llm.tool_calls import (
    extract_textual_tool_calls,
    extract_truncated_tool_calls,
    looks_like_leaked_tool_markup,
    resolve_textual_turn,
    strip_tool_call_markup,
    tool_call_has_required_args,
    tool_call_objects,
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


def test_resolve_textual_turn_recovers_closed_block() -> None:
    text = '<tool_call>\n{"name": "list_directory", "arguments": {"path": "app"}}\n</tool_call>'
    turn = resolve_textual_turn(
        text,
        tools=[{"type": "function", "function": {"name": "list_directory"}}],
    )
    assert turn.kind == "tools"
    objs = tool_call_objects(turn.tool_calls)
    assert objs[0].function.name == "list_directory"
    assert "app" in objs[0].function.arguments


def test_resolve_textual_turn_retries_broken_qwen_leak() -> None:
    text = '<tool_call>\n{"name": "list_directory", "arguments": {"path>}}]}}]}}]}}]}}]}}'
    turn = resolve_textual_turn(text)
    assert turn.kind == "retry"
    assert "tool_call" in turn.nudge


def test_recover_truncated_write_file_gitignore_loop() -> None:
    text = (
        "Now let me create the `.gitignore`:\n\n"
        "<tool_call>\n"
        '{"name": "write_file", "arguments": {"path": '
        '"/tmp/data_address/.gitignore", "content": '
        '"# Python\\n__pycache__/\\n*.py[cod]\\n\\n# Testing\\n.pytest_cache/\\n'
        "# Pytest\\n.pytest_cache/\\n# Ruff\\n.ruff_cache/\\n"
        "# Pytest\\n.pytest_cache/\\n# Ruff\\n.ruff_cache/\\n"
        "# Pytest\\n.pytest_cache/\\n# Ruff\\n.ruff_cache/"
    )
    turn = resolve_textual_turn(
        text,
        tools=[{"type": "function", "function": {"name": "write_file"}}],
    )
    assert turn.kind == "tools"
    args = json.loads(turn.tool_calls[0]["function"]["arguments"])
    assert args["path"].endswith(".gitignore")
    assert "__pycache__" in args["content"]
    assert args["content"].count("# Pytest") < 3


def test_write_file_without_args_is_not_recovered() -> None:
    text = '<tool_call>{"name": "write_file", "arguments": {}}</tool_call>'
    tools = [{"type": "function", "function": {"name": "write_file"}}]
    assert extract_textual_tool_calls(text, tools=tools) == []
    turn = resolve_textual_turn(text, tools=tools)
    assert turn.kind == "retry"
    assert (
        tool_call_objects(
            [
                {
                    "id": "x",
                    "type": "function",
                    "function": {"name": "write_file", "arguments": "{}"},
                }
            ]
        )
        == []
    )


def test_write_file_empty_content_is_allowed() -> None:
    call = {
        "id": "x",
        "type": "function",
        "function": {
            "name": "write_file",
            "arguments": json.dumps({"path": "app/__init__.py", "content": ""}),
        },
    }
    assert tool_call_has_required_args(call) is True


def test_first_choice_message_handles_empty_llm() -> None:
    assert first_choice_message(None) is None
    assert is_empty_llm_response(None) is True
    empty = type("R", (), {"choices": None})()
    assert first_choice_message(empty) is None
    assert is_empty_llm_response(empty) is True
    msg = object()
    ok = type("R", (), {"choices": [type("C", (), {"message": msg})()]})()
    assert first_choice_message(ok) is msg


def test_blank_final_text_is_not_a_finished_answer() -> None:
    assert is_blank_final_text("")
    assert is_blank_final_text("   ")
    assert is_blank_final_text("No response")
    assert is_blank_final_text("No response generated")
    assert not is_blank_final_text("patched providers.py")


def test_extract_truncated_read_file_with_path_only() -> None:
    text = '<tool_call>\n{"name": "read_file", "arguments": {"path": "app/main.py"}'
    calls = extract_truncated_tool_calls(
        text,
        tools=[{"type": "function", "function": {"name": "read_file"}}],
    )
    assert calls[0]["function"]["name"] == "read_file"
    assert "main.py" in calls[0]["function"]["arguments"]


def test_resolve_textual_turn_plain_final() -> None:
    turn = resolve_textual_turn("PROCESS_APPROVE — tests are green.")
    assert turn.kind == "final"
    assert "PROCESS_APPROVE" in turn.final_text
