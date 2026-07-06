"""Web research intent detection and sub-agent direct dispatch."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.direct_dispatch.search_intent import extract_search_topic, is_web_research_request
from core.direct_dispatch.web_research import try_web_research_subagent_dispatch
from core.subagents.manager import SubAgentManager
from core.tools.registry import ToolRegistry


def test_is_web_research_route_fuel_ru() -> None:
    msg = "Проверь, работают ли заправки по трассе М-11 из Москвы в Петрозаводск сегодня"
    assert is_web_research_request(msg)


def test_is_web_research_natural_search() -> None:
    msg = "Найди в интернете информацию по запуску SaaS агентов"
    assert is_web_research_request(msg)
    assert extract_search_topic(msg) is not None


def test_is_not_web_research_small_talk() -> None:
    assert not is_web_research_request("Привет")
    assert not is_web_research_request("спасибо")
    assert not is_web_research_request("ты тут?")


def test_is_not_web_research_local_tasks() -> None:
    assert not is_web_research_request("Напиши функцию на Python для сортировки")
    assert not is_web_research_request("Создай файл config.yaml")
    assert not is_web_research_request("/subagents")
    assert not is_web_research_request("что делаешь?")


def test_is_web_research_fuel_problem_variants() -> None:
    assert is_web_research_request("проблема с бензином в Петрозаводске")
    assert is_web_research_request("Какая ситуация с бензином на М-11")
    assert is_web_research_request("Как обстановка на М-11 сегодня?")


def test_is_web_research_route_planning() -> None:
    assert is_web_research_request("По какой дороге лучше ехать из москвы в мурманск")
    assert is_web_research_request("Какой маршрут быстрее до Петрозаводска")


def test_is_web_research_general_questions() -> None:
    assert is_web_research_request("Какой курс доллара сегодня")
    assert is_web_research_request("Сколько стоит iPhone 16 в России")
    assert is_web_research_request("Кто CEO OpenAI")
    assert is_web_research_request("Расскажи про последний релиз Python")
    assert is_web_research_request("What is the weather in Helsinki today?")


def test_is_web_research_implicit_search_verbs() -> None:
    assert is_web_research_request("Узнай когда выходит новый сезон сериала")
    assert is_web_research_request("Проверь открыт ли сегодня аэропорт Шереметьево")


@pytest.mark.asyncio
async def test_try_web_research_subagent_dispatch_roundtrip() -> None:
    parent = MagicMock()
    parent.model = "test-model"
    parent.config = SimpleNamespace(
        enable_subagents=True,
        subagent_max_concurrent=4,
        subagent_default_process_mode="async",
        subagent_process_timeout=30.0,
        profile_name="default",
        confirmation_timeout=0,
        mcp_assignments={},
    )
    parent.skills = None
    parent.memory = None
    parent.tools = ToolRegistry(profile_name="default")
    parent.tools.register_all()

    message = MagicMock()
    message.content = "SYNTHESIZED_WEB_ANSWER"
    message.tool_calls = None
    choice = MagicMock(message=message)
    response = MagicMock(choices=[choice])
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    parent.client = client
    parent.subagents = SubAgentManager(parent)

    notices: list[str] = []

    async def capture_notice(text: str) -> None:
        notices.append(text)

    handled, body = await try_web_research_subagent_dispatch(
        parent,
        "Проверь статус АЗС на М-11 сегодня",
        timeout_seconds=30.0,
        notify=capture_notice,
    )
    assert handled is True
    assert "SYNTHESIZED_WEB_ANSWER" in body
    assert len(notices) == 1
    assert "web_researcher" in notices[0].lower() or "Субагент" in notices[0]


@pytest.mark.asyncio
async def test_try_web_research_spawn_only_returns_job_id() -> None:
    parent = MagicMock()
    parent.model = "test-model"
    parent.config = SimpleNamespace(
        enable_subagents=True,
        subagent_max_concurrent=4,
        subagent_default_process_mode="async",
        subagent_process_timeout=30.0,
        profile_name="default",
        confirmation_timeout=0,
        mcp_assignments={},
    )
    parent.skills = None
    parent.memory = None
    parent.tools = ToolRegistry(profile_name="default")
    parent.tools.register_all()
    parent.subagents = SubAgentManager(parent)

    handled, job_id = await try_web_research_subagent_dispatch(
        parent,
        "Найди в интернете последние новости про Holix AI agent",
        wait_for_result=False,
    )
    assert handled is True
    assert job_id == "web_researcher"
    handle = parent.subagents.get_handle(job_id)
    assert handle is not None
    assert handle.is_running


@pytest.mark.asyncio
async def test_try_web_research_dispatch_murmansk_route() -> None:
    parent = MagicMock()
    parent.config = SimpleNamespace(
        enable_subagents=True,
        subagent_max_concurrent=4,
        subagent_default_process_mode="async",
        subagent_process_timeout=30.0,
        profile_name="default",
        confirmation_timeout=0,
        mcp_assignments={},
    )
    parent.skills = None
    parent.memory = None
    parent.tools = ToolRegistry(profile_name="default")
    parent.tools.register_all()
    parent.subagents = SubAgentManager(parent)

    handled, job_id = await try_web_research_subagent_dispatch(
        parent,
        "По какой дороге лучше ехать из москвы в мурманск",
        wait_for_result=False,
    )
    assert handled is True
    assert job_id == "web_researcher"