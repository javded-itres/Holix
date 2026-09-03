"""Session self-diagnose: intent, heuristics, skill rewrite, honesty nudge."""

from __future__ import annotations

from core.direct_dispatch.intent import is_self_diagnose_request
from core.graph.action_honesty import (
    SELF_DIAGNOSE_NUDGE,
    honesty_retry_update,
    should_nudge_self_diagnose,
)
from core.runtime.self_diagnose import (
    diagnose_session,
    is_wrong_chat_delivery_skill,
    rewrite_delivery_skill,
)
from core.tools.lazy_schema import CORE_TOOL_NAMES
from core.tools.slot_policy import PLAN_MODE_ALLOWED, tool_allowed_for_slot


def test_self_diagnose_intent_positive() -> None:
    assert is_self_diagnose_request("проверь себя")
    assert is_self_diagnose_request("Почему ты делаешь не так?")
    assert is_self_diagnose_request("Ты отвечаешь неправильно")
    assert is_self_diagnose_request("check yourself")
    assert is_self_diagnose_request("You're answering incorrectly")
    assert is_self_diagnose_request("самодиагностика")
    assert is_self_diagnose_request("проанализируй свою сессию")


def test_self_diagnose_intent_negative() -> None:
    assert not is_self_diagnose_request("проверь config.yaml")
    assert not is_self_diagnose_request("почему это не работает")
    assert not is_self_diagnose_request("напиши функцию на Python")
    assert not is_self_diagnose_request("что делаешь?")
    assert not is_self_diagnose_request("Привет")


def test_diagnose_claimed_send_without_tool() -> None:
    report = diagnose_session(
        complaint="проверь себя",
        messages=[
            {"role": "user", "content": "Пришли в чат файлы md"},
            {"role": "assistant", "content": "Вот оба файла полностью в чат."},
            {"role": "user", "content": "Я не вижу файлов"},
            {"role": "assistant", "content": "Отправил файлы ещё раз."},
            {"role": "user", "content": "отправь ещё раз"},
            {"role": "assistant", "content": "Готово, файлы в чате."},
            {"role": "user", "content": "проверь себя"},
        ],
        trajectory=[
            {"type": "tool_call_start", "tool_name": "read_file"},
            {"type": "tool_call_start", "tool_name": "run_terminal_command"},
            {
                "type": "llm_call_completed",
                "model": "test",
                "total_tokens": 100,
                "finish_reason": "stop",
            },
        ],
    )
    codes = {f["code"] for f in report["findings"]}
    assert "claimed_file_send_without_tool" in codes
    assert "repeated_user_complaint" in codes
    assert report["llm"]["llm_calls"] == 1
    assert "send_chat_files" not in report["session"]["distinct_tools"]


def test_rewrite_wrong_delivery_skill() -> None:
    content = """## When to Use
- Пользователь просит пришли файлы в чат.

## Procedure
1. split -l 80 file.md part_
2. Отправь каждую часть через read_file.

## Pitfalls
- Не используй cat.

## Verification
- Пользователь видит содержимое.
"""
    assert is_wrong_chat_delivery_skill(content)
    patched = rewrite_delivery_skill(content)
    assert patched is not None
    assert "send_chat_files" in patched
    assert "split -l" not in patched
    assert "## When to Use" in patched
    assert not is_wrong_chat_delivery_skill(patched)


def test_self_diagnose_nudge_when_model_skips_tool() -> None:
    state = {
        "honesty_nudge_count": 0,
        "user_input": "проверь себя",
        "messages": [{"role": "user", "content": "проверь себя"}],
    }
    assert should_nudge_self_diagnose(
        state,
        final_response="Извини, сейчас исправлюсь.",
        messages=state["messages"],
    )
    update = honesty_retry_update(
        messages=list(state["messages"]),
        step_count=1,
        final_response="Извини, сейчас исправлюсь.",
        user_input="проверь себя",
    )
    assert update["is_final"] is False
    assert update["messages"][-1]["content"] == SELF_DIAGNOSE_NUDGE


def test_self_diagnose_no_nudge_after_tool() -> None:
    messages = [
        {"role": "user", "content": "проверь себя"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "1", "function": {"name": "self_diagnose"}}],
        },
        {"role": "tool", "name": "self_diagnose", "tool_call_id": "1", "content": '{"ok": true}'},
    ]
    state = {"honesty_nudge_count": 0, "user_input": "проверь себя", "messages": messages}
    assert not should_nudge_self_diagnose(
        state,
        final_response="Нашёл: не вызывался send_chat_files.",
        messages=messages,
    )


def test_self_diagnose_is_core_and_main_slot() -> None:
    assert "self_diagnose" in CORE_TOOL_NAMES
    assert tool_allowed_for_slot("self_diagnose", "main")
    assert not tool_allowed_for_slot("self_diagnose", "coder")
    assert "self_diagnose" in PLAN_MODE_ALLOWED
