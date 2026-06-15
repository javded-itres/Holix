"""Direct intent detection for fast-path dispatch."""

from __future__ import annotations

from core.direct_dispatch import (
    is_status_request,
    is_subagent_list_request,
    is_work_activity_request,
    should_answer_work_status,
)


def test_status_request_ru() -> None:
    assert is_status_request("какой статус?")
    assert is_status_request("Какой статус задачи?")


def test_subagent_list_request() -> None:
    assert is_subagent_list_request("/subagents")
    assert is_subagent_list_request("список субагентов")


def test_work_activity_request_ru() -> None:
    assert is_work_activity_request("что делаешь?")
    assert should_answer_work_status("что ты делаешь")