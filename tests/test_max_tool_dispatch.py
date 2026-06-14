"""MAX direct tool dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from integrations.max.tool_dispatch import (
    _extract_search_topic,
    _extract_web_search_query,
    _is_status_request,
    _needs_analysis,
    _split_search_and_analysis,
    try_direct_tool_dispatch,
)


def test_extract_web_search_explicit_call() -> None:
    q = _extract_web_search_query('Вызови web_search("SaaS AI agents launch") и пришли результат')
    assert q == "SaaS AI agents launch"


def test_extract_web_search_natural_ru() -> None:
    q = _extract_web_search_query("Найди в интернете информацию по запуску SaaS Агентов")
    assert q is not None
    assert "SaaS" in q


def test_extract_web_search_typo_interenete() -> None:
    q = _extract_web_search_query("Найди в интеренете информацию по запуску SaaS Агентов")
    assert q is not None
    assert "SaaS" in q


def test_repeat_search_marker() -> None:
    assert _extract_web_search_query("Еще раз повтори поиск") == "__REPEAT__"


def test_status_request_detected() -> None:
    assert _is_status_request("Покажи полный статус системы")
    assert _is_status_request("Какой статус задачи?")


def test_analysis_request_splits_search_topic() -> None:
    msg = (
        "Найди в интеренете информацию по запуску SaaS Агентов "
        "проанализируй информацию и скажи стоит ли делать свое решение"
    )
    assert _needs_analysis(msg)
    search_part, analysis_part = _split_search_and_analysis(msg)
    topic = _extract_search_topic(search_part)
    assert topic is not None
    assert "SaaS" in topic
    assert "проанализируй" in analysis_part.lower()


@pytest.mark.asyncio
async def test_direct_web_search_runs_tool_and_replies() -> None:
    tool = MagicMock()
    tool.execute = AsyncMock(return_value="result line 1\nresult line 2")

    agent = MagicMock()
    agent.tools.tools = {"web_search": tool}
    agent.tools._action_guard = None
    agent.emit = MagicMock()

    host = MagicMock()
    host.agent = agent
    host.conversation_id = "max_default_1"
    host._send_text = AsyncMock()

    handled, body = await try_direct_tool_dispatch(
        host,
        'web_search("test query")',
    )

    assert handled is True
    assert "result line 1" in body
    tool.execute.assert_awaited_once_with(query="test query", max_results=8)
    host._send_text.assert_awaited()
    assert agent.emit.call_count == 2


@pytest.mark.asyncio
async def test_search_with_analysis_returns_synthesis_not_links() -> None:
    tool = MagicMock()
    tool.execute = AsyncMock(
        return_value="1. **SaaS guide**\n   snippet\n   URL: https://example.com"
    )

    choice = MagicMock()
    choice.message.content = (
        "Рынок SaaS-агентов растёт. Свое решение имеет смысл, если есть ниша. "
        "Риски: конкуренция и инфраструктура."
    )
    response = MagicMock()
    response.choices = [choice]

    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)

    agent = MagicMock()
    agent.tools.tools = {"web_search": tool}
    agent.tools._action_guard = None
    agent.client = client
    agent.model = "smart"
    agent.emit = MagicMock()

    host = MagicMock()
    host.agent = agent
    host.conversation_id = "max_default_1"
    host._send_text = AsyncMock()
    host._interactive = MagicMock()

    msg = (
        "Найди в интеренете информацию по запуску SaaS Агентов "
        "проанализируй информацию и скажи стоит ли делать свое решение"
    )
    handled, body = await try_direct_tool_dispatch(host, msg)

    assert handled is True
    assert "📊 Анализ" in body
    assert "смысл" in body.lower() or "риск" in body.lower()
    assert "https://example.com" not in body
    client.chat.completions.create.assert_awaited_once()