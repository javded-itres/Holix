"""Human-readable sub-agent tool output for messenger UIs."""

from __future__ import annotations

import json
from typing import Any

_SUBAGENT_RESULT_TOOLS = frozenset(
    {
        "wait_subagent_result",
        "delegate_to_subagent",
        "list_subagents",
        "terminate_subagent",
    }
)


def _loads_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def format_subagent_tool_notice(tool_name: str, body: str) -> str:
    """Turn sub-agent tool JSON into a short chat notice."""
    name = (tool_name or "").strip()
    text = (body or "").strip()
    if not text:
        return ""

    if name == "wait_subagent_result":
        return _format_wait_result(text) or text
    if name == "delegate_to_subagent":
        return _format_delegate_result(text) or text
    if name == "list_subagents":
        return _format_list_subagents(text)
    if name == "terminate_subagent":
        return f"Субагент `{text}`" if text else text

    return text


def extract_subagent_tool_text(tool_name: str, body: str) -> str:
    """Extract user-visible text from a sub-agent tool result."""
    name = (tool_name or "").strip()
    text = (body or "").strip()
    if not text:
        return ""

    if name == "wait_subagent_result":
        formatted = _format_wait_result(text)
        return formatted or text

    if name == "delegate_to_subagent":
        data = _loads_json(text)
        if data and data.get("status") == "spawned":
            return ""
        return _format_delegate_result(text) or text

    if name in {"list_subagents", "terminate_subagent"}:
        return format_subagent_tool_notice(name, text)

    return text


def pick_best_tool_final(recent_tools: list[dict[str, Any]]) -> str:
    """Pick the best tool output to use when the model returns no final text."""
    if not recent_tools:
        return ""

    for entry in reversed(recent_tools):
        name = str(entry.get("name") or "").strip()
        body = str(entry.get("full_result") or "").strip()
        if not body:
            continue
        if name == "wait_subagent_result":
            text = extract_subagent_tool_text(name, body)
            if text:
                return text
        if name not in _SUBAGENT_RESULT_TOOLS and name != "send_chat_files":
            text = extract_subagent_tool_text(name, body) or body
            if text:
                return text

    for entry in reversed(recent_tools):
        name = str(entry.get("name") or "").strip()
        body = str(entry.get("full_result") or "").strip()
        if not body:
            continue
        text = extract_subagent_tool_text(name, body)
        if text:
            return text

    last = recent_tools[-1]
    return str(last.get("full_result") or "").strip()


def _format_wait_result(raw: str) -> str:
    data = _loads_json(raw)
    if not data:
        return raw

    job_id = str(data.get("job_id") or "?")
    if not data.get("success"):
        err = (data.get("error") or "субагент завершился с ошибкой").strip()
        return f"**Субагент `{job_id}`:** ✗ {err}"

    response = (data.get("response") or "").strip()
    if response:
        return f"**Субагент `{job_id}`:**\n\n{response}"
    err = (data.get("error") or "").strip()
    if err:
        return f"**Субагент `{job_id}`:** ✗ {err}"
    return f"**Субагент `{job_id}`** завершил работу без текста."


def _format_list_subagents(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return "Субагенты: нет данных."

    data = _loads_json(text)
    if not data:
        return text

    total = int(data.get("total") or 0)
    running = int(data.get("running") or 0)
    agents = data.get("agents") or []

    if total == 0:
        return (
            "**Субагенты:** сейчас нет запущенных задач.\n\n"
            "Запуск вручную: `/subagent-spawn researcher <задача>`\n"
            "Или напишите агенту: «делегируй researcher: …»"
        )

    lines = [f"**Субагенты:** {total} (в работе: {running})"]
    for item in agents[:12]:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or "?"
        status = item.get("status") or "?"
        preview = (item.get("task_preview") or item.get("agent_type") or "")[:80]
        line = f"• `{name}` — {status}"
        if preview:
            line += f" — {preview}"
        lines.append(line)
    return "\n".join(lines)


def _format_delegate_result(raw: str) -> str:
    data = _loads_json(raw)
    if not data:
        return raw

    if data.get("status") == "spawned":
        job_id = str(data.get("job_id") or "?")
        agent_type = str(data.get("agent_type") or "?")
        return (
            f"**Субагент запущен:** `{job_id}` ({agent_type})\n"
            "Результат придёт отдельным сообщением, когда задача завершится."
        )

    return str(data.get("message") or raw).strip()