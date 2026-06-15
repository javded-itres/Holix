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
    assert not is_aborted_final_response("Вот готовый ответ на ваш вопрос.")


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