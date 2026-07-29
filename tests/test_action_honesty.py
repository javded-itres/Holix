"""Action honesty: do not accept unproven completion claims."""

from __future__ import annotations

from core.graph.action_honesty import (
    ACTION_HONESTY_NUDGE,
    SDD_FILL_HONESTY_NUDGE,
    SDD_FILL_HONESTY_REFUSAL,
    WORKSPACE_GROUNDING_NUDGE,
    claims_action_completed,
    claims_empty_or_deaf_tools,
    claims_sdd_artifacts_filled,
    denies_visible_workspace,
    ends_turn_on_unexecuted_intent,
    has_successful_workspace_listing,
    honesty_refusal_update,
    honesty_retry_update,
    is_sdd_fill_request,
    lacks_evidence_for_claim,
    resolve_tool_choice,
    sdd_fill_requires_tools,
    should_nudge_false_completion,
    should_refuse_unproven_sdd_fill,
    successful_tools_since_last_user,
)
from core.graph.builder import prepare_initial_state


def test_claims_completion_ru_and_en() -> None:
    assert claims_action_completed("Готово! План сохранён в файл.")
    assert claims_action_completed("I've saved the plan to disk.")
    assert claims_action_completed("Successfully created the project.")
    assert claims_action_completed("Готово. Заполнил все четыре артефакта.")
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


def test_sdd_create_change_not_enough_for_spec_filled_claim() -> None:
    """Scaffolding a change is not evidence that the spec was filled."""
    messages = [
        {"role": "user", "content": "Создай спеку new_user"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "sdd_create_change", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "content": '{"ok": true, "change_id": "new_user", "filled": false}',
        },
    ]
    assert lacks_evidence_for_claim(
        "Готово, спека new_user создана и заполнена.",
        messages,
    )


def test_sdd_write_artifact_allows_spec_claim() -> None:
    messages = [
        {"role": "user", "content": "Заполни спеку"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "sdd_write_artifact", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "content": '{"ok": true, "path": "openspec/changes/new_user/specs/auth/spec.md"}',
        },
    ]
    assert not lacks_evidence_for_claim(
        "Заполнил delta-спеку через sdd_write_artifact.",
        messages,
    )


def test_studio_sdd_fill_claim_without_write_is_blocked() -> None:
    """UI auto-prompt after create_change: pure text 'Заполнил' is not enough."""
    user = (
        "SDD change `new-user` created in project `user_catalog`.\n"
        "User request:\nNeed a watcher\n\n"
        "MUST call sdd_write_artifact for proposal, design, delta specs, and tasks."
    )
    claim = (
        "Готово. Заполнил все четыре артефакта SDD change `new-user`.\n"
        "| Proposal | `user_catalog/openspec/changes/new-user/proposal.md` | 1250 chars |"
    )
    messages = [
        {"role": "user", "content": user},
        {"role": "assistant", "content": claim},
    ]
    assert is_sdd_fill_request(user)
    assert claims_sdd_artifacts_filled(claim)
    assert lacks_evidence_for_claim(claim, messages)
    assert sdd_fill_requires_tools(messages)
    assert should_nudge_false_completion(
        {"honesty_nudge_count": 0, "user_input": user},
        final_response=claim,
        messages=messages,
    )
    # Stuck checkpoint count must not block after reset path (count still 0 each turn)
    assert should_nudge_false_completion(
        {"honesty_nudge_count": 1, "user_input": user},
        final_response=claim,
        messages=messages,
    )
    # After max SDD nudges, stop nudging — but refuse the false final instead
    assert not should_nudge_false_completion(
        {"honesty_nudge_count": 3, "user_input": user},
        final_response=claim,
        messages=messages,
    )
    assert should_refuse_unproven_sdd_fill(
        {"honesty_nudge_count": 3, "user_input": user},
        final_response=claim,
        messages=messages,
    )
    refusal = honesty_refusal_update(
        messages=messages,
        step_count=4,
        honesty_nudge_count=3,
        include_assistant=False,
        final_response=claim,
    )
    assert refusal["is_final"] is True
    assert refusal["final_response"] == SDD_FILL_HONESTY_REFUSAL
    assert "sdd_write_artifact" in refusal["final_response"]
    assert refusal["messages"][-1]["content"] == SDD_FILL_HONESTY_REFUSAL


def test_sdd_fill_tool_choice_required_until_write() -> None:
    user = (
        "SDD change `x` created in project `p`.\n"
        "Please fill proposal via sdd_write_artifact."
    )
    messages = [{"role": "user", "content": user}]
    state = {"user_input": user, "tool_results": []}
    # Without sdd_write_artifact in schemas → required
    assert resolve_tool_choice(state, messages, tools=[{"type": "function"}]) == "required"
    # With schema → force that function
    forced = resolve_tool_choice(
        state,
        messages,
        tools=[
            {
                "type": "function",
                "function": {"name": "sdd_write_artifact", "parameters": {}},
            }
        ],
    )
    assert forced == {
        "type": "function",
        "function": {"name": "sdd_write_artifact"},
    }
    messages_with_write = messages + [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "sdd_write_artifact", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "name": "sdd_write_artifact",
            "content": '{"ok": true, "path": "openspec/changes/x/proposal.md"}',
        },
    ]
    assert (
        resolve_tool_choice(
            {"user_input": user, "tool_results": []},
            messages_with_write,
            tools=[{"type": "function"}],
        )
        == "auto"
    )


def test_prepare_initial_state_resets_honesty_nudge() -> None:
    state = prepare_initial_state(agent=None, user_input="hi")
    assert state["honesty_nudge_count"] == 0


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


def test_sdd_honesty_retry_uses_sdd_nudge() -> None:
    user = "SDD change `x` created.\nPlease fill via sdd_write_artifact."
    out = honesty_retry_update(
        messages=[{"role": "user", "content": user}],
        step_count=1,
        final_response="Готово. Заполнил все четыре артефакта.",
        honesty_nudge_count=0,
        user_input=user,
    )
    assert out["messages"][-1]["content"] == SDD_FILL_HONESTY_NUDGE


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


def test_empty_workspace_claim_denied_when_listing_succeeded() -> None:
    messages = [
        {"role": "user", "content": "Запусти it-resources-site"},
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
            "name": "list_directory",
            "content": (
                "Contents of /var/lib/holix/profiles/x/workspace:\n"
                "[DIR]  it-resources-site\n"
                "[DIR]  it_rs_vue"
            ),
        },
    ]
    claim = (
        "В workspace сейчас нет папки it-resources-site (workspace практически пустой). "
        "Инструменты возвращают пустые ответы."
    )
    assert claims_empty_or_deaf_tools(claim)
    assert has_successful_workspace_listing(messages)
    assert denies_visible_workspace(claim, messages)
    assert should_nudge_false_completion(
        {"honesty_nudge_count": 0},
        final_response=claim,
        messages=messages,
    )
    out = honesty_retry_update(
        messages=messages,
        step_count=1,
        final_response=claim,
        honesty_nudge_count=0,
    )
    assert out["messages"][-1]["content"] == WORKSPACE_GROUNDING_NUDGE


def test_empty_claim_without_listing_is_not_workspace_nudge() -> None:
    messages = [{"role": "user", "content": "Что в workspace?"}]
    claim = "Workspace пуст, list_directory ничего не вернул."
    assert claims_empty_or_deaf_tools(claim)
    assert not has_successful_workspace_listing(messages)
    assert not denies_visible_workspace(claim, messages)
