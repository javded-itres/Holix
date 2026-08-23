"""Messenger routing for sub-agent questions (Telegram / MAX)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from core.subagents.interaction import SubAgentInteractionBridge
from integrations.messenger.subagent_reply import (
    apply_reply_button,
    ensure_job_token,
    job_id_from_reply,
    remember_question_message,
    route_messenger_text,
    tokens_for_jobs,
)


def _agent_with_questions(*names: str) -> tuple[MagicMock, SubAgentInteractionBridge]:
    parent = MagicMock()
    parent.events = MagicMock()
    bridge = SubAgentInteractionBridge(parent, confirmation_timeout=5)
    parent.subagents = MagicMock()
    parent.subagents.interactions = bridge
    loop = asyncio.get_running_loop()
    bridge._question_meta = {}
    for i, name in enumerate(names, start=1):
        rid = f"subq_{i}"
        bridge._pending_questions[rid] = loop.create_future()
        bridge._question_meta[rid] = {"subagent_name": name, "question": f"q{i}?"}
    return parent, bridge


@pytest.mark.asyncio
async def test_route_messenger_text_shows_picker_not_cli_hint() -> None:
    agent, _bridge = _agent_with_questions("coder-1", "coder")
    session = SimpleNamespace(
        subagent_reply_job_id=None,
        subagent_pending_answer=None,
        subagent_question_message_ids={},
    )
    routed = route_messenger_text(agent, session, "use pytest")
    assert routed.kind == "need_target"
    assert session.subagent_pending_answer == "use pytest"
    assert "/subagent-reply" not in (routed.feedback or "")


@pytest.mark.asyncio
async def test_apply_reply_button_delivers_pending_answer() -> None:
    agent, bridge = _agent_with_questions("coder-1", "coder")
    session = SimpleNamespace(
        subagent_reply_job_id=None,
        subagent_pending_answer="use pytest",
        subagent_question_message_ids={},
    )
    routed = apply_reply_button(agent, session, "coder-1")
    assert routed.kind == "delivered"
    assert routed.job_id == "coder-1"
    assert session.subagent_pending_answer is None
    rid = next(iter(bridge._pending_questions))
    assert bridge._pending_questions[rid].result() == "use pytest"


@pytest.mark.asyncio
async def test_reply_to_question_message_routes_answer() -> None:
    agent, bridge = _agent_with_questions("coder-1", "coder")
    session = SimpleNamespace(
        subagent_reply_job_id=None,
        subagent_pending_answer=None,
        subagent_question_message_ids={},
    )
    remember_question_message(session, 42, "coder")
    assert job_id_from_reply(session, 42) == "coder"
    routed = route_messenger_text(agent, session, "REST", reply_to_message_id=42)
    assert routed.kind == "delivered"
    assert routed.job_id == "coder"
    # second pending future is coder
    future = bridge._pending_questions["subq_2"]
    assert future.result() == "REST"


def test_ensure_job_token_stable() -> None:
    mapping: dict[str, str] = {}
    a = ensure_job_token(mapping, "coder-1")
    b = ensure_job_token(mapping, "coder")
    c = ensure_job_token(mapping, "coder-1")
    assert a == c
    assert a != b
    tokens = tokens_for_jobs(mapping, ["coder-1", "coder"])
    assert tokens["coder-1"] == a
    assert tokens["coder"] == b


def test_format_subagent_question_includes_job_and_locale() -> None:
    from integrations.messenger.subagent_question_ui import (
        format_subagent_question_message,
        mark_question_posted,
    )

    text = format_subagent_question_message(
        job_id="coder-2",
        question="Какое изменение сделать?",
        context="tool: read_file",
        locale="ru",
        html=False,
    )
    assert "coder-2" in text
    assert "Субагент" in text
    assert "Какое изменение сделать?" in text
    assert "Нажмите кнопку" in text
    assert "Sub-agent" not in text

    html = format_subagent_question_message(
        job_id="coder-2",
        question="<b>x</b>",
        locale="ru",
        html=True,
    )
    assert "&lt;b&gt;x&lt;/b&gt;" in html
    assert "<b>" in html

    session = SimpleNamespace()
    assert mark_question_posted(session, "subq_1") is True
    assert mark_question_posted(session, "subq_1") is False
    assert mark_question_posted(session, "subq_2") is True


def test_telegram_reply_keyboard_uses_sr_callback() -> None:
    pytest.importorskip("aiogram.types")
    from integrations.telegram.keyboards import subagent_reply_keyboard

    kb = subagent_reply_keyboard({"coder-1": "deadbeef"}, locale="ru")
    assert kb is not None
    btn = kb.inline_keyboard[0][0]
    assert "coder-1" in btn.text
    assert btn.callback_data == "hx:sr:deadbeef"
