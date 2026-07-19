"""Action honesty: do not accept unproven completion claims."""

from __future__ import annotations

from core.graph.action_honesty import (
    ACTION_HONESTY_NUDGE,
    claims_action_completed,
    ends_turn_on_unexecuted_intent,
    honesty_retry_update,
    lacks_evidence_for_claim,
    should_nudge_false_completion,
    successful_tools_since_last_user,
)


def test_claims_completion_ru_and_en() -> None:
    assert claims_action_completed("Готово! План сохранён в файл.")
    assert claims_action_completed("I've saved the plan to disk.")
    assert claims_action_completed("Successfully created the project.")
    assert not claims_action_completed("Что нужно сделать?")
    assert not claims_action_completed("Сейчас сохраню план через write_file.")


def test_no_tools_means_lacks_evidence() -> None:
    messages = [
        {"role": "user", "content": "Сохрани план"},
        {"role": "assistant", "content": "План сохранён."},
    ]
    assert lacks_evidence_for_claim("План сохранён в TMS.md", messages)


def test_list_only_not_enough_for_write_claim() -> None:
    messages = [
        {"role": "user", "content": "Сохрани план"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "list_directory", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "content": "Contents of /workspace: [DIR] .holix",
        },
    ]
    assert lacks_evidence_for_claim(
        "Рабочая директория пустая. План сохранён как TMS.md.",
        messages,
    )


def test_write_file_success_allows_claim() -> None:
    messages = [
        {"role": "user", "content": "Сохрани план"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "write_file", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "content": "Wrote 1200 bytes to TMS.md",
        },
    ]
    assert not lacks_evidence_for_claim("Готово, план сохранён в TMS.md.", messages)
    assert successful_tools_since_last_user(messages) == ["write_file"]


def test_failed_tool_does_not_count() -> None:
    messages = [
        {"role": "user", "content": "Удали проекты"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "run_terminal_command", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "content": "Error (exit code 1): Permission denied",
        },
    ]
    assert lacks_evidence_for_claim("Готово, все проекты удалены.", messages)


def test_nudge_once_then_stop() -> None:
    state = {"honesty_nudge_count": 0, "messages": []}
    messages = [{"role": "user", "content": "save"}]
    assert should_nudge_false_completion(
        state, final_response="Готово, файл создан.", messages=messages
    )
    state["honesty_nudge_count"] = 1
    assert not should_nudge_false_completion(
        state, final_response="Готово, файл создан.", messages=messages
    )


def test_honesty_retry_update_appends_nudge() -> None:
    out = honesty_retry_update(
        messages=[{"role": "user", "content": "x"}],
        step_count=2,
        final_response="План сохранён.",
        honesty_nudge_count=0,
    )
    assert out["is_final"] is False
    assert out["honesty_nudge_count"] == 1
    assert out["messages"][-1]["content"] == ACTION_HONESTY_NUDGE
    assert out["messages"][-2]["role"] == "assistant"


def test_plan_mode_skips_honesty_nudge() -> None:
    state = {
        "honesty_nudge_count": 0,
        "plan_steps": [{"step": 1}],
        "current_plan_step": 0,
    }
    assert not should_nudge_false_completion(
        state,
        final_response="Готово, файл создан.",
        messages=[{"role": "user", "content": "x"}],
    )


def test_promise_without_tools_is_nudged() -> None:
    messages = [{"role": "user", "content": "Запиши план сейчас"}]
    assert ends_turn_on_unexecuted_intent(
        "Выполняю запись файла прямо сейчас.",
        messages,
    )
    assert should_nudge_false_completion(
        {"honesty_nudge_count": 0},
        final_response="Сейчас сохраню план через write_file.",
        messages=messages,
    )
