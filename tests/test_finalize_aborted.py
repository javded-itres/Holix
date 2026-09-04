"""Post-finalize work must not block messenger runs after LLM timeout/errors."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.graph.nodes.finalize_node import finalize_node
from core.presenters.final_content import is_aborted_final_response


def test_is_aborted_final_response_detects_llm_timeout() -> None:
    assert is_aborted_final_response("Модель не ответила за 120 с. Попробуйте ещё раз.")
    assert is_aborted_final_response("Error: Command blocked. Path is outside the workspace.")
    assert is_aborted_final_response("Error during agent step: Request timed out.")
    assert not is_aborted_final_response("Вот готовый ответ на ваш вопрос.")


def test_is_aborted_final_response_ignores_exception_type_in_source() -> None:
    """Source dumps with TimeoutError: must not look like an aborted run."""
    dump = (
        "notifications router lines:\n \n85\n\n"
        ' 1: """Operator notifications via Server-Sent Events."""\n'
        "40:             except TimeoutError:\n"
        '41:                 event = {"type": "keepalive"}\n'
        "71:     except AuthorizationError as exc:\n"
        "72:         raise HTTPException(\n"
    )
    assert not is_aborted_final_response(dump)
    from core.subagents.react_agent import is_failed_react_result

    assert is_failed_react_result(dump) is None


@pytest.mark.asyncio
async def test_finalize_skips_slow_postprocess_on_timeout() -> None:
    agent = MagicMock()
    agent.tools._action_guard = MagicMock()
    agent.memory.auto_summarize_conversation = AsyncMock(
        side_effect=lambda *args, **kwargs: asyncio.sleep(60)
    )
    agent.skills.should_create_skill = AsyncMock(return_value=True)
    agent.config = SimpleNamespace(auto_summarize_conversations=True)

    state = {
        "conversation_id": "test",
        "messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "x"}],
        "final_response": "Модель не ответила за 120 с. Попробуйте ещё раз.",
        "plan_status": "",
        "step_count": 1,
    }
    config = {"configurable": {"_agent": agent}}

    started = time.monotonic()
    await finalize_node(state, config)
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    agent.memory.auto_summarize_conversation.assert_not_called()
    agent.skills.should_create_skill.assert_not_called()
