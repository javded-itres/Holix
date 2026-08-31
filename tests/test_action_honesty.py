"""Action honesty: do not accept unproven completion claims."""

from __future__ import annotations

from core.graph.action_honesty import (
    ACTION_HONESTY_NUDGE,
    MONOLOGUE_HONESTY_REFUSAL,
    MONOLOGUE_TOOL_NUDGE,
    SDD_FILL_HONESTY_NUDGE,
    SDD_FILL_HONESTY_REFUSAL,
    UNFINISHED_STEP_NUDGE,
    WORKSPACE_GROUNDING_NUDGE,
    claims_action_completed,
    claims_empty_or_deaf_tools,
    claims_sdd_artifacts_filled,
    denies_visible_workspace,
    ends_turn_on_unexecuted_intent,
    has_successful_workspace_listing,
    honesty_refusal_update,
    honesty_retry_update,
    is_action_request,
    is_sdd_fill_request,
    is_truncation_notice,
    lacks_evidence_for_claim,
    looks_like_clarifying_questions,
    looks_like_plan_monologue,
    looks_like_status_monologue,
    looks_like_unfinished_work_announcement,
    resolve_tool_choice,
    sdd_fill_requires_tools,
    should_nudge_false_completion,
    should_nudge_introspect_final,
    should_refuse_status_monologue,
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


def test_clarifying_questions_are_not_unexecuted_intent() -> None:
    text = (
        "Хочешь FastAPI-сервис для каталога книг. Прежде чем писать код, "
        "давай определимся со спецификацией. Несколько вопросов:\n\n"
        "1. Хранение: память или SQLite?\n"
        "2. Поля книги: только название и автор?\n\n"
        "Ответь, пожалуйста, и я распишу план и потом напишу код."
    )
    assert looks_like_clarifying_questions(text)
    assert not ends_turn_on_unexecuted_intent(
        text,
        [{"role": "user", "content": "напиши на fastapi каталог книг"}],
        user_input="напиши на fastapi каталог книг",
        agent_pipeline="modern",
    )
    state = {
        "honesty_nudge_count": 0,
        "messages": [{"role": "user", "content": "напиши на fastapi каталог книг"}],
        "user_input": "напиши на fastapi каталог книг",
        "agent_pipeline": "modern",
    }
    assert not should_nudge_false_completion(state, final_response=text, messages=state["messages"])


def test_plan_monologue_without_tools_is_nudged() -> None:
    monologue = (
        "Поняла. Нужно добавить боту функцию.\n\n"
        "Что сделаю:\n"
        "• Изучу структуру проекта.\n"
        "• Найду, где бот генерирует пост.\n\n"
        "Начинаю."
    )
    assert looks_like_plan_monologue(monologue)
    messages = [
        {"role": "user", "content": "Добавь обработку URL"},
        {"role": "assistant", "content": monologue},
    ]
    assert ends_turn_on_unexecuted_intent(monologue, messages, user_input="Добавь обработку URL")
    state = {
        "user_input": "Добавь обработку URL",
        "messages": messages,
        "tool_results": [],
        "honesty_nudge_count": 0,
        "plan_steps": [],
        "current_plan_step": 0,
    }
    assert should_nudge_false_completion(
        state,
        final_response=monologue,
        messages=messages,
    )


def test_truncation_notice_without_tools_is_nudged_not_final() -> None:
    """Modern pipeline: finish_reason=length must not be a final without tools."""
    notice = (
        "… Поняла. Ищу свежие IT-новости за сегодня.\n\n"
        "Ответ обрезан лимитом токенов модели. Остановилась, не повторяя фразу — "
        "попросите продолжить, сузьте задачу или выберите модель с большим бюджетом ответа."
    )
    assert is_truncation_notice(notice)
    messages = [
        {"role": "user", "content": "Сделай тестовый пост, новости IT за сегодня"},
        {"role": "assistant", "content": notice},
    ]
    assert ends_turn_on_unexecuted_intent(
        notice,
        messages,
        user_input="Сделай тестовый пост, новости IT за сегодня",
        agent_pipeline="modern",
    )
    state = {
        "user_input": "Сделай тестовый пост, новости IT за сегодня",
        "messages": messages,
        "tool_results": [],
        "honesty_nudge_count": 0,
        "plan_steps": [],
        "current_plan_step": 0,
        "agent_pipeline": "modern",
    }
    assert should_nudge_false_completion(state, final_response=notice, messages=messages)
    out = honesty_retry_update(
        messages=list(messages),
        step_count=1,
        final_response=notice,
        honesty_nudge_count=0,
        user_input="Сделай тестовый пост, новости IT за сегодня",
        include_assistant=False,
    )
    assert out["is_final"] is False
    assert out["messages"][-1]["content"] == MONOLOGUE_TOOL_NUDGE
    tools = [{"type": "function", "function": {"name": "web_search"}}]
    assert (
        resolve_tool_choice(
            {**state, "honesty_nudge_count": 1},
            out["messages"],
            tools=tools,
        )
        == "required"
    )


def test_classic_blocks_intent_only_halfway_stop() -> None:
    """Classic must not accept «Создаю пост…» without tools as a finished task."""
    monologue = "Поняла. Создаю тестовый пост с IT-новостями за сегодня. Ищу свежие новости."
    messages = [
        {"role": "user", "content": "Сделай тестовый пост, новости IT за сегодня"},
        {"role": "assistant", "content": monologue},
    ]
    assert ends_turn_on_unexecuted_intent(
        monologue,
        messages,
        user_input="Сделай тестовый пост, новости IT за сегодня",
        agent_pipeline="classic",
    )
    state = {
        "user_input": "Сделай тестовый пост, новости IT за сегодня",
        "messages": messages,
        "tool_results": [],
        "honesty_nudge_count": 0,
        "plan_steps": [],
        "current_plan_step": 0,
        "agent_pipeline": "classic",
    }
    assert should_nudge_false_completion(state, final_response=monologue, messages=messages)
    out = honesty_retry_update(
        messages=list(messages),
        step_count=1,
        final_response=monologue,
        honesty_nudge_count=0,
        user_input="Сделай тестовый пост, новости IT за сегодня",
        include_assistant=False,
    )
    assert out["is_final"] is False
    tools = [{"type": "function", "function": {"name": "web_search"}}]
    assert (
        resolve_tool_choice(
            {**state, "honesty_nudge_count": 1},
            out["messages"],
            tools=tools,
        )
        == "required"
    )
    from core.graph.action_honesty import _MAX_HONESTY_NUDGES

    refuse_state = {**state, "honesty_nudge_count": _MAX_HONESTY_NUDGES}
    assert should_refuse_status_monologue(refuse_state, final_response=monologue, messages=messages)


def test_action_request_forces_tools_on_first_step() -> None:
    assert is_action_request("Сделай тестовый пост, новости IT за сегодня")
    assert is_action_request("делай")
    tools = [{"type": "function", "function": {"name": "read_file"}}]
    state = {
        "user_input": "Сделай тестовый пост, новости IT за сегодня",
        "messages": [
            {"role": "user", "content": "Сделай тестовый пост, новости IT за сегодня"},
        ],
        "tool_results": [],
        "honesty_nudge_count": 0,
        "plan_steps": [],
        "current_plan_step": 0,
        "agent_pipeline": "modern",
    }
    assert resolve_tool_choice(state, state["messages"], tools=tools) == "required"
    # Classic also forces tools on action requests (no mid-task stop).
    classic = {**state, "agent_pipeline": "classic"}
    assert resolve_tool_choice(classic, classic["messages"], tools=tools) == "required"


def test_status_monologue_poniala_proveryayu_loop_is_nudged() -> None:
    """User-reported TG spam: «Поняла. Проверяю статус бота через MCP…» × N."""
    cycle = "Поняла. Проверяю статус бота через MCP.…"
    monologue = "Проверяю статус бота через MCP-инструмент.…" + cycle * 20
    assert looks_like_status_monologue(monologue) or ends_turn_on_unexecuted_intent(
        monologue,
        [{"role": "user", "content": "Проверь бота"}],
        user_input="Проверь бота",
    )
    messages = [
        {"role": "user", "content": "Проверь статус бота"},
        {"role": "assistant", "content": monologue},
    ]
    assert ends_turn_on_unexecuted_intent(
        monologue,
        messages,
        user_input="Проверь статус бота",
        agent_pipeline="classic",
    )


def test_classic_blocks_zapuskayu_bot_py_loop() -> None:
    """Prod: classic finished on 18KB of «…Поняла. Запускаю bot.py…» without tools."""
    unit = "…Поняла. Запускаю бота `javded_content_bot.py` в фоновом процессе."
    monologue = unit * 80
    messages = [
        {"role": "user", "content": "да"},
        {"role": "assistant", "content": monologue},
    ]
    assert ends_turn_on_unexecuted_intent(
        monologue,
        messages,
        user_input="да",
        agent_pipeline="classic",
    )
    state = {
        "user_input": "Проверь статус бота",
        "messages": messages,
        "tool_results": [],
        "honesty_nudge_count": 0,
        "plan_steps": [],
        "current_plan_step": 0,
        "agent_pipeline": "classic",
    }
    assert should_nudge_false_completion(state, final_response=monologue, messages=messages)


def test_status_monologue_mcp_spam_is_nudged_and_forced_tools() -> None:
    """Radical anti-spam: «Да. Смотрю mcp_server.py…» without tools."""
    monologue = "Да. Смотрю mcp_server.py, чтобы добавить publish_news."
    assert looks_like_status_monologue(monologue)
    assert looks_like_plan_monologue(monologue)
    messages = [
        {"role": "user", "content": "Добавь publish_news в MCP"},
        {"role": "assistant", "content": monologue},
    ]
    assert ends_turn_on_unexecuted_intent(
        monologue, messages, user_input="Добавь publish_news в MCP"
    )
    state = {
        "user_input": "Добавь publish_news в MCP",
        "messages": messages,
        "tool_results": [],
        "honesty_nudge_count": 0,
        "plan_steps": [],
        "current_plan_step": 0,
        "agent_pipeline": "modern",
    }
    assert should_nudge_false_completion(state, final_response=monologue, messages=messages)
    out = honesty_retry_update(
        messages=messages,
        step_count=1,
        final_response=monologue,
        honesty_nudge_count=0,
        user_input="Добавь publish_news в MCP",
        include_assistant=False,
    )
    assert out["messages"][-1]["content"] == MONOLOGUE_TOOL_NUDGE
    assert out["is_final"] is False
    tools = [{"type": "function", "function": {"name": "read_file"}}]
    # After honesty nudge, tool_choice must be required (soft text is not enough).
    assert (
        resolve_tool_choice(
            {**state, "honesty_nudge_count": 1},
            out["messages"],
            tools=tools,
        )
        == "required"
    )
    # After max nudges still monologuing → refuse, do not accept spam as final.
    from core.graph.action_honesty import _MAX_HONESTY_NUDGES

    refuse_state = {**state, "honesty_nudge_count": _MAX_HONESTY_NUDGES}
    assert not should_nudge_false_completion(
        refuse_state, final_response=monologue, messages=messages
    )
    assert should_refuse_status_monologue(refuse_state, final_response=monologue, messages=messages)
    refused = honesty_refusal_update(
        messages=messages,
        step_count=2,
        honesty_nudge_count=_MAX_HONESTY_NUDGES,
        include_assistant=False,
        final_response=monologue,
        refusal=MONOLOGUE_HONESTY_REFUSAL,
    )
    assert refused["is_final"] is True
    assert "инструмент" in refused["final_response"].lower()


def test_check_then_finish_intent_is_nudged() -> None:
    monologue = "Сейчас проверю текущее состояние кода и процесса, а затем доделаю меню."
    assert looks_like_plan_monologue(monologue)
    messages = [
        {"role": "user", "content": "Доделай меню"},
        {"role": "assistant", "content": monologue},
    ]
    assert ends_turn_on_unexecuted_intent(monologue, messages, user_input="Доделай меню")


def test_plan_monologue_not_nudged_on_pure_faq() -> None:
    monologue = "Что сделаю: подумаю и отвечу. Начинаю."
    messages = [
        {"role": "user", "content": "Что такое Holix?"},
        {"role": "assistant", "content": monologue},
    ]
    assert looks_like_plan_monologue(monologue)
    assert not ends_turn_on_unexecuted_intent(monologue, messages, user_input="Что такое Holix?")


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
    user = "SDD change `x` created in project `p`.\nPlease fill proposal via sdd_write_artifact."
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


def test_write_file_counts_as_sdd_artifact_evidence() -> None:
    """Analysis agents persist docs with write_file — that is enough for SDD claims."""
    user = (
        "SDD change `shopapi-1` created in project `shop_api`.\n"
        "MUST call sdd_write_artifact for proposal, design, delta specs, and tasks."
    )
    messages = [
        {"role": "user", "content": user},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "w1",
                    "type": "function",
                    "function": {"name": "write_file", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "w1",
            "content": "Wrote 15230 bytes to openspec/changes/shopapi-1/analysis/analysis-coder.md",
        },
    ]
    claim = "Готово. Заполнил analysis в openspec/changes/shopapi-1/analysis/analysis-coder.md"
    assert is_sdd_fill_request(user)
    assert claims_sdd_artifacts_filled(claim)
    assert not lacks_evidence_for_claim(claim, messages)
    assert not sdd_fill_requires_tools(messages, user_input=user)
    assert not should_nudge_false_completion(
        {"honesty_nudge_count": 0, "user_input": user},
        final_response=claim,
        messages=messages,
    )


def test_honesty_nudge_does_not_wipe_write_file_evidence() -> None:
    messages = [
        {"role": "user", "content": "Write the analysis docs"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "w1",
                    "type": "function",
                    "function": {"name": "write_file", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "w1",
            "content": "Wrote 2000 bytes to analysis.md",
        },
        {"role": "user", "content": "[Action honesty] You stated that work was completed"},
        {"role": "assistant", "content": "Готово, файл analysis.md создан."},
    ]
    assert successful_tools_since_last_user(messages) == ["write_file"]
    assert not lacks_evidence_for_claim("Готово, файл analysis.md создан.", messages)


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
    from core.graph.action_honesty import _MAX_HONESTY_NUDGES

    state = {"honesty_nudge_count": 0, "messages": []}
    messages = [{"role": "user", "content": "save"}]
    assert should_nudge_false_completion(
        state, final_response="Готово, файл создан.", messages=messages
    )
    state["honesty_nudge_count"] = _MAX_HONESTY_NUDGES
    assert not should_nudge_false_completion(
        state, final_response="Готово, файл создан.", messages=messages
    )


def test_introspect_echo_is_nudged_not_final() -> None:
    from core.runtime.introspect_signals import INTROSPECT_REFUSAL, INTROSPECT_WRITE_NUDGE

    refusal = INTROSPECT_REFUSAL
    assert should_nudge_introspect_final(final_response=refusal, messages=[])
    messages = [
        {"role": "user", "content": "почини тест оплаты"},
        {
            "role": "tool",
            "content": refusal,
        },
    ]
    assert should_nudge_introspect_final(final_response=refusal, messages=messages)
    out = honesty_retry_update(
        messages=messages,
        step_count=40,
        final_response=refusal,
        honesty_nudge_count=0,
    )
    assert out["is_final"] is False
    assert out["final_response"] == ""
    assert INTROSPECT_WRITE_NUDGE in out["messages"][-1]["content"]
    assert "dadata" not in out["messages"][-1]["content"].lower()


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


def test_honesty_retry_code_mode_asks_for_run_code() -> None:
    out = honesty_retry_update(
        messages=[{"role": "user", "content": "x"}],
        step_count=2,
        final_response="План сохранён.",
        honesty_nudge_count=0,
        tools_presentation="code",
    )
    text = out["messages"][-1]["content"]
    assert text.startswith("[Action honesty]")
    assert "run_code" in text
    assert "Code mode" in text
    native = honesty_retry_update(
        messages=[{"role": "user", "content": "x"}],
        step_count=2,
        final_response="План сохранён.",
        honesty_nudge_count=0,
        tools_presentation="native",
    )
    assert native["messages"][-1]["content"] == ACTION_HONESTY_NUDGE


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


def test_let_me_start_after_tools_is_not_a_finished_step() -> None:
    reply = (
        "Let me take a step back and create all the files properly. Let me start with the models:"
    )
    assert looks_like_unfinished_work_announcement(reply)
    messages = [
        {"role": "user", "content": "Собери FastAPI каталог"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "function": {"name": "write_file"}}],
        },
        {"role": "tool", "name": "write_file", "content": "created app/config.py"},
        {"role": "assistant", "content": reply},
    ]
    # Tools already ran — the old intent check would have accepted this.
    assert not ends_turn_on_unexecuted_intent(reply, messages, user_input="Собери FastAPI каталог")
    state = {
        "user_input": "Собери FastAPI каталог",
        "messages": messages,
        "tool_results": [{"name": "write_file", "result": "created"}],
        "honesty_nudge_count": 0,
        "plan_steps": [],
        "current_plan_step": 0,
    }
    assert should_nudge_false_completion(state, final_response=reply, messages=messages)
    out = honesty_retry_update(
        messages=list(messages),
        step_count=4,
        final_response=reply,
        honesty_nudge_count=0,
        user_input="Собери FastAPI каталог",
        include_assistant=False,
    )
    assert out["is_final"] is False
    assert out["messages"][-1]["content"] == UNFINISHED_STEP_NUDGE
    assert not looks_like_unfinished_work_announcement(
        "Created app/models.py and tests. pytest: 8 passed."
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


def test_spisok_pust_scrubbed_when_listing_exists() -> None:
    from core.graph.action_honesty import scrub_false_empty_claim_content

    claim = "Список пуст. Проверю рабочую директорию напрямую. Похоже, текущая сессия ограничена и"
    messages = [
        {"role": "user", "content": "ls"},
        {
            "role": "tool",
            "name": "list_directory",
            "content": "Contents of w:\n[DIR]  it-resources-site\n[DIR]  openspec",
        },
    ]
    assert claims_empty_or_deaf_tools(claim)
    assert denies_visible_workspace(claim, messages)
    assert scrub_false_empty_claim_content(claim, messages) == ""


def test_prod_phrases_returned_empty_and_zero_dirs() -> None:
    claim = (
        "Павел, все три команды вернули пусто. Если коротко — **вижу ноль каталогов**. "
        "В твоём profile workspace сейчас действительно нет ни одной директории. "
        "Файлы it-resources-site сейчас физически отсутствуют на диске."
    )
    messages = [
        {"role": "user", "content": "какие директории"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "list_directory", "arguments": "{}"},
                },
                {
                    "id": "c2",
                    "type": "function",
                    "function": {"name": "sdd_list_projects", "arguments": "{}"},
                },
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "name": "list_directory",
            "content": ("Contents of workspace:\n[DIR]  it-resources-site\n[DIR]  openspec"),
        },
        {
            "role": "tool",
            "tool_call_id": "c2",
            "name": "sdd_list_projects",
            "content": (
                '{\n  "ok": true,\n  "projects": [\n'
                '    {"path": "it-resources-site", "label": "it-resources-site"}\n'
                "  ]\n}"
            ),
        },
    ]
    assert claims_empty_or_deaf_tools(claim)
    assert denies_visible_workspace(claim, messages)
    assert should_nudge_false_completion(
        {"honesty_nudge_count": 0},
        final_response=claim,
        messages=messages,
    )


def test_empty_result_phrase_and_hard_refusal() -> None:
    from core.graph.action_honesty import (
        should_refuse_false_empty_workspace,
        workspace_grounding_refusal_text,
    )

    claim = (
        "инструменты в этом сеансе упрямо возвращают пустой результат — "
        "и read_file, и run_terminal_command"
    )
    messages = [
        {"role": "user", "content": "openspec"},
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
            "content": ("Contents of workspace:\n[DIR]  it-resources-site\n[DIR]  openspec"),
        },
    ]
    assert claims_empty_or_deaf_tools(claim)
    assert denies_visible_workspace(claim, messages)
    state = {"honesty_nudge_count": 2}
    assert should_refuse_false_empty_workspace(state, final_response=claim, messages=messages)
    text = workspace_grounding_refusal_text(messages)
    assert "it-resources-site" in text
    assert "openspec" in text
