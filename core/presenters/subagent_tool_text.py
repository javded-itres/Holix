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


def _tool_entry_name_body(entry: dict[str, Any]) -> tuple[str, str]:
    name = str(entry.get("name") or entry.get("tool_name") or "").strip()
    body = str(
        entry.get("full_result") or entry.get("result") or entry.get("content") or ""
    ).strip()
    return name, body


def graph_tool_results_as_recent(tool_results: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Normalize LangGraph tool_results to messenger {name, full_result} rows."""
    recent: list[dict[str, Any]] = []
    for entry in tool_results or []:
        if not isinstance(entry, dict):
            continue
        name, body = _tool_entry_name_body(entry)
        if name or body:
            recent.append({"name": name, "full_result": body})
    return recent


def _item_label(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return str(item).strip()
    return str(
        item.get("label")
        or item.get("name")
        or item.get("path")
        or item.get("remote_id")
        or item.get("id")
        or ""
    ).strip()


def _format_named_list(title: str, items: list[Any], *, limit: int = 30) -> list[str]:
    lines = [f"**{title}:**"]
    shown = 0
    for item in items:
        label = _item_label(item)
        if not label:
            continue
        extra = ""
        if isinstance(item, dict):
            kind = str(item.get("kind") or item.get("path") or "").strip()
            if kind and kind != label:
                extra = f" (`{kind}`)"
        lines.append(f"- {label}{extra}")
        shown += 1
        if shown >= limit:
            remaining = len(items) - shown
            if remaining > 0:
                lines.append(f"- …ещё {remaining}")
            break
    return lines if shown else []


def format_tool_body_for_messenger(body: str, *, name: str = "") -> str:
    """Turn raw tool output (MCP JSON, listings) into a short chat answer."""
    text = (body or "").strip()
    if not text:
        return ""
    data = _loads_json(text)
    if data is None:
        if len(text) > 3500:
            return text[:3490].rstrip() + "…"
        return text

    if data.get("ok") is False:
        err = str(data.get("error") or data.get("detail") or "ошибка").strip()
        tool = name or "tool"
        return f"Ошибка `{tool}`: {err}"

    share = data.get("share") if isinstance(data.get("share"), dict) else {}
    item = data.get("item") if isinstance(data.get("item"), dict) else {}
    url = str(
        share.get("public_url")
        or data.get("public_url")
        or item.get("web_view_url")
        or data.get("web_view_url")
        or ""
    ).strip()
    title = str(share.get("name") or item.get("name") or data.get("name") or name or "Файл").strip()
    if url:
        return f"**{title}**\n{url}"

    lines: list[str] = []
    for key, heading in (
        ("sdd_projects", "SDD-проекты"),
        ("projects", "Проекты Studio"),
        ("ide_projects", "IDE-проекты"),
        ("items", "Файлы и папки"),
        ("agents", "Субагенты"),
    ):
        raw_items = data.get(key)
        if isinstance(raw_items, list) and raw_items:
            lines.extend(_format_named_list(heading, raw_items))
    if lines:
        return "\n".join(lines)

    if name in _SUBAGENT_RESULT_TOOLS:
        return extract_subagent_tool_text(name, text) or text

    compact = json.dumps(data, ensure_ascii=False)
    if len(compact) > 1200:
        compact = compact[:1190].rstrip() + "…"
    return compact


def _looks_like_tool_error(name: str, body: str, formatted: str) -> bool:
    if formatted.lower().startswith("ошибка"):
        return True
    if body.lower().startswith("error"):
        return True
    if '"ok": false' in body[:200].lower():
        return True
    if name == "delegate_to_subagent" and '"status": "spawned"' in body.lower():
        return True
    return False


def pick_best_tool_final(recent_tools: list[dict[str, Any]]) -> str:
    """Pick the best tool output to use when the model returns no final text."""
    if not recent_tools:
        return ""

    from core.runtime.test_run_signals import is_test_log_dump

    errors: list[str] = []
    for entry in reversed(recent_tools):
        if not isinstance(entry, dict):
            continue
        name, body = _tool_entry_name_body(entry)
        if not body:
            continue
        if name == "wait_subagent_result":
            text = extract_subagent_tool_text(name, body)
            if text and not is_test_log_dump(text):
                return text
        if name == "send_chat_files":
            continue
        formatted = format_tool_body_for_messenger(body, name=name)
        if not formatted:
            continue
        if is_test_log_dump(body) or is_test_log_dump(formatted):
            continue
        if _looks_like_tool_error(name, body, formatted):
            errors.append(formatted)
            continue
        return formatted

    for entry in reversed(recent_tools):
        if not isinstance(entry, dict):
            continue
        name, body = _tool_entry_name_body(entry)
        if not body or is_test_log_dump(body):
            continue
        text = extract_subagent_tool_text(name, body)
        if text and not is_test_log_dump(text):
            return text

    if errors:
        return errors[0]
    return ""


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


def extract_delegate_job_id(body: str) -> str | None:
    """Return job_id from delegate_to_subagent JSON, if spawn succeeded."""
    data = _loads_json((body or "").strip())
    if not data:
        return None
    status = str(data.get("status") or "").strip()
    if status not in {"spawned", "already_running"}:
        return None
    job_id = str(data.get("job_id") or "").strip()
    return job_id or None


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
