"""Automatic session_doctor when a turn contradicts tool results."""

from __future__ import annotations

from types import SimpleNamespace

from core.graph.nodes.react_node import _maybe_honesty_retry
from core.runtime.auto_session_doctor import (
    auto_session_doctor_enabled,
    should_auto_session_doctor,
    tool_loop_reason,
)


def _call(name: str, args: str, tool_id: str) -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": tool_id, "function": {"name": name, "arguments": args}}],
    }


def _result(tool_id: str, content: str) -> dict:
    return {"role": "tool", "tool_call_id": tool_id, "content": content}


def test_auto_session_doctor_defaults_on_and_profile_can_disable() -> None:
    assert auto_session_doctor_enabled(None) is True
    assert auto_session_doctor_enabled(SimpleNamespace(config=SimpleNamespace())) is True
    off = SimpleNamespace(config=SimpleNamespace(auto_session_doctor=False))
    assert auto_session_doctor_enabled(off) is False


def test_identical_tool_calls_are_a_loop() -> None:
    messages = [{"role": "user", "content": "прочитай README"}]
    for i in range(4):
        messages.append(_call("read_file", '{"path": "README"}', str(i)))
        messages.append(_result(str(i), "hello"))
    assert tool_loop_reason(messages) == "tool_loop:read_file"


def test_three_consecutive_errors_of_one_tool() -> None:
    messages = [{"role": "user", "content": "отправь файл"}]
    for i, args in enumerate(('{"path": "a"}', '{"path": "b"}', '{"path": "c"}')):
        messages.append(_call("send_chat_files", args, str(i)))
        messages.append(_result(str(i), "Error: not sent"))
    assert tool_loop_reason(messages) == "tool_errors:send_chat_files"


def test_repeated_invented_task_id_starts_the_doctor() -> None:
    messages = [
        {"role": "user", "content": "запусти тесты"},
        {"role": "assistant", "content": "task_deadbeef ещё идёт"},
        {"role": "user", "content": "[Action honesty] Do not invent task ids."},
    ]
    state = {"honesty_nudge_count": 1, "user_input": "запусти тесты"}
    assert (
        should_auto_session_doctor(
            state,
            final_response="Задача task_deadbeef ещё выполняется",
            messages=messages,
            exhausted_claims=False,
        )
        == "invented_task_id"
    )


def test_first_unproven_claim_stays_an_honesty_nudge() -> None:
    messages = [{"role": "user", "content": "сохрани файл"}]
    state = {"honesty_nudge_count": 0, "user_input": "сохрани файл"}
    final = "Готово, файл сохранён."
    assert (
        should_auto_session_doctor(
            state,
            final_response=final,
            messages=messages,
        )
        == ""
    )
    update = _maybe_honesty_retry(
        state,
        messages=messages,
        step_count=1,
        final_response=final,
        assistant_already_appended=False,
        agent=SimpleNamespace(config=SimpleNamespace(auto_session_doctor=True)),
    )
    assert update is not None
    assert update["is_final"] is False
    assert "[Action honesty]" in update["messages"][-1]["content"]


def test_exhausted_unproven_claim_spawns_the_doctor_once() -> None:
    messages = [{"role": "user", "content": "сохрани файл"}]
    state = {
        "honesty_nudge_count": 3,
        "user_input": "сохрани файл",
        "conversation_id": "c1",
    }
    final = "Готово, файл сохранён."
    agent = SimpleNamespace(
        config=SimpleNamespace(auto_session_doctor=True),
        agent_slot="main",
        emit=lambda _event: None,
    )
    update = _maybe_honesty_retry(
        state,
        messages=messages,
        step_count=4,
        final_response=final,
        assistant_already_appended=False,
        agent=agent,
    )
    assert update is not None
    text = update["messages"][-1]["content"]
    assert text.startswith("[Self-diagnose]")
    assert "session_doctor" in text
    again = _maybe_honesty_retry(
        state,
        messages=messages,
        step_count=5,
        final_response=final,
        assistant_already_appended=False,
        agent=agent,
    )
    assert again is None


def test_disabled_profile_keeps_the_unproven_final() -> None:
    messages = [{"role": "user", "content": "сохрани файл"}]
    state = {"honesty_nudge_count": 3, "user_input": "сохрани файл"}
    agent = SimpleNamespace(
        config=SimpleNamespace(auto_session_doctor=False),
        agent_slot="main",
    )
    assert (
        _maybe_honesty_retry(
            state,
            messages=list(messages),
            step_count=4,
            final_response="Готово, файл сохранён.",
            assistant_already_appended=False,
            agent=agent,
        )
        is None
    )


def test_status_monologue_does_not_start_the_doctor() -> None:
    messages = [{"role": "user", "content": "почини бота"}]
    state = {"honesty_nudge_count": 3, "user_input": "почини бота"}
    assert (
        should_auto_session_doctor(
            state,
            final_response="Поняла. Проверяю бота.",
            messages=messages,
        )
        == ""
    )


def test_session_doctor_slot_does_not_spawn_itself() -> None:
    messages = [{"role": "user", "content": "разбери сессию"}]
    for i in range(4):
        messages.append(_call("read_file", '{"path": "README"}', str(i)))
        messages.append(_result(str(i), "hello"))
    agent = SimpleNamespace(config=SimpleNamespace(), agent_slot="session_doctor")
    assert (
        should_auto_session_doctor(
            {"honesty_nudge_count": 0},
            final_response="",
            messages=messages,
            agent=agent,
        )
        == ""
    )
