"""MAX sub-agent message formatting."""

from core.direct_dispatch import is_status_request, is_subagent_list_request
from integrations.max.subagent_format import format_list_subagents_result


def test_format_empty_subagents_list() -> None:
    out = format_list_subagents_result(
        '{"total": 0, "running": 0, "completed": 0, "failed": 0, '
        '"cancelled": 0, "timed_out": 0, "agents": []}'
    )
    assert "нет запущенных" in out.lower()
    assert "/subagent-spawn" in out


def test_status_request_does_not_hijack_subagent_actions() -> None:
    assert not is_status_request("Запусти субагента researcher для анализа рынка")
    assert not is_status_request("Делегируй задачу субагенту")
    assert is_status_request("Покажи полный статус системы")
    assert is_status_request("Какой статус задачи?")


def test_subagent_list_patterns() -> None:
    assert is_subagent_list_request("/subagents")
    assert is_subagent_list_request("список субагентов")