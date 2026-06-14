"""Run Helix tools directly from MAX chat — bypass LLM when intent is clear."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

_REPEAT_SEARCH_RE = re.compile(
    r"(?:повтори|ещё?\s*раз|снова)\s+(?:поиск|search)",
    re.IGNORECASE,
)
_WEB_SEARCH_CALL_RE = re.compile(
    r"web_search\s*\(\s*['\"](.+?)['\"]\s*\)",
    re.IGNORECASE | re.DOTALL,
)
_WEB_SEARCH_TOPIC_RES = (
    re.compile(
        r"найди\s+(?:в\s+)?(?:интернете?|интеренете?|сети|web)\s+"
        r"(?:информацию\s+)?(?:по\s+)?(.+)$",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"поиск(?:ай)?\s+(?:в\s+)?(?:интернете?|интеренете?|сети)?\s*(.+)$",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"search(?:\s+the\s+web|\s+online)?\s+for\s+(.+)$",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"исследуй\s+(?:тему\s+)?(.+)$",
        re.IGNORECASE | re.DOTALL,
    ),
)
_ANALYSIS_TRIGGER_RE = re.compile(
    r"\s+(?:"
    r"проанализируй(?:те)?|анализ(?:ируй(?:те)?)?|"
    r"изучи(?:те)?|разбери(?:те)?|оцени(?:те)?|"
    r"скажи\s+стоит\s+ли|сделай\s+вывод|подведи\s+итог|"
    r"дай\s+(?:рекомендацию|заключение|совет)|"
    r"analyze|summarize"
    r")\b",
    re.IGNORECASE,
)
_SUBAGENT_LIST_RE = re.compile(
    r"(?:"
    r"^/subagents?$|"
    r"^list_subagents\s*\(\s*\)$|"
    r"^список\s+субагентов|"
    r"^покажи\s+субагентов|"
    r"^list\s+subagents$"
    r")",
    re.IGNORECASE,
)
_STATUS_RE = re.compile(
    r"(?:"
    r"^/status$|^статус$|^status$|"
    r"полный\s+статус|"
    r"какой\s+статус|какие\s+задачи|"
    r"что\s+выполняется|"
    r"^покажи\s+статус"
    r")",
    re.IGNORECASE,
)


def _clean_query(raw: str) -> str:
    q = (raw or "").strip().strip("«»\"'.")
    q = re.split(r"\s+и\s+пришли", q, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    return q[:500]


def _extract_search_topic(text: str) -> str | None:
    explicit = _WEB_SEARCH_CALL_RE.search(text)
    if explicit:
        return _clean_query(explicit.group(1))

    stripped = text.strip()
    for pattern in _WEB_SEARCH_TOPIC_RES:
        match = pattern.search(stripped)
        if match:
            q = _clean_query(match.group(1))
            if len(q) >= 3:
                return q
    return None


def _extract_web_search_query(text: str) -> str | None:
    if _REPEAT_SEARCH_RE.search(text):
        return "__REPEAT__"
    return _extract_search_topic(text)


def _needs_analysis(text: str) -> bool:
    return bool(_ANALYSIS_TRIGGER_RE.search(text.strip()))


def _split_search_and_analysis(text: str) -> tuple[str, str]:
    """Split user message into (search_fragment, analysis_instruction)."""
    stripped = text.strip()
    match = _ANALYSIS_TRIGGER_RE.search(stripped)
    if not match:
        return stripped, stripped
    search_part = stripped[: match.start()].strip()
    analysis_part = stripped[match.start():].strip()
    return search_part or stripped, analysis_part or stripped


def _is_status_request(text: str) -> bool:
    return bool(_STATUS_RE.search(text.strip()))


async def _last_search_query(host: Any, agent: Any, conversation_id: str) -> str | None:
    store = getattr(getattr(host, "_session", None), "_transcript_store", None)
    if store is not None:
        for entry in reversed(getattr(store, "entries", [])):
            if entry.kind != "user":
                continue
            q = _extract_web_search_query(entry.plain)
            if q and q != "__REPEAT__":
                return q

    memory = getattr(agent, "memory", None)
    if memory is None:
        return None
    try:
        recent = await memory.get_recent_messages(conversation_id, limit=24)
    except Exception:
        return None
    for msg in reversed(recent or []):
        if msg.get("role") != "user":
            continue
        q = _extract_web_search_query(str(msg.get("content") or ""))
        if q and q != "__REPEAT__":
            return q
    return None


async def try_direct_tool_dispatch(host: Any, message: str) -> tuple[bool, str]:
    """Execute tools or built-in MAX actions without full agent loop when intent is clear."""
    agent = getattr(host, "agent", None)
    if not agent or not getattr(agent, "tools", None):
        return False, ""

    text = (message or "").strip()
    if not text:
        return False, ""

    conversation_id = getattr(host, "conversation_id", "default")

    if _SUBAGENT_LIST_RE.match(text):
        logger.info("MAX direct dispatch: list_subagents")
        return await _run_tool(host, agent, conversation_id, "list_subagents", {})

    if _is_status_request(text):
        logger.info("MAX direct dispatch: status")
        await host._interactive.show_status()
        cfg = getattr(agent, "config", None)
        if cfg and getattr(cfg, "enable_subagents", True):
            _, sub_body = await _run_tool(
                host, agent, conversation_id, "list_subagents", {}
            )
            return True, sub_body
        return True, ""

    if _needs_analysis(text):
        search_part, analysis_part = _split_search_and_analysis(text)
        query = _extract_search_topic(search_part)
        if query:
            logger.info(
                "MAX direct dispatch: web_search+analyze (%r)",
                query[:80],
            )
            return await _run_search_and_analyze(
                host,
                agent,
                conversation_id,
                user_message=text,
                search_query=query,
                analysis_instruction=analysis_part,
            )

    query = _extract_web_search_query(text)
    if query == "__REPEAT__":
        query = await _last_search_query(host, agent, conversation_id)
        if not query:
            return True, (
                "Уточните поисковый запрос, например:\n"
                'web_search("SaaS AI agents launch")'
            )

    if query:
        logger.info("MAX direct dispatch: web_search (%r)", query[:80])
        return await _run_tool(
            host,
            agent,
            conversation_id,
            "web_search",
            {"query": query, "max_results": 8},
        )

    return False, ""


async def _run_search_and_analyze(
    host: Any,
    agent: Any,
    conversation_id: str,
    *,
    user_message: str,
    search_query: str,
    analysis_instruction: str,
) -> tuple[bool, str]:
    handled, raw = await _run_tool(
        host,
        agent,
        conversation_id,
        "web_search",
        {"query": search_query, "max_results": 8},
        preview_to_chat=False,
    )
    if not handled:
        return False, ""

    if raw.startswith("✗") or raw.startswith("Error"):
        return True, raw

    await host._send_text("🧠 Готовлю анализ на основе найденных материалов…")

    try:
        analysis = await _synthesize_analysis(
            agent,
            user_message=user_message,
            search_query=search_query,
            analysis_instruction=analysis_instruction,
            search_results=raw,
        )
    except Exception as exc:
        logger.exception("MAX search analysis failed")
        return True, (
            f"Поиск выполнен, но анализ не удался: {exc}\n\n"
            f"Сырые результаты:\n{raw[:2000]}"
        )

    logger.info("MAX search analysis done (%d chars)", len(analysis))
    body = analysis if len(analysis) <= 3800 else analysis[:3780] + "…"
    return True, f"**📊 Анализ**\n\n{body}"


async def _synthesize_analysis(
    agent: Any,
    *,
    user_message: str,
    search_query: str,
    analysis_instruction: str,
    search_results: str,
) -> str:
    client = getattr(agent, "client", None)
    model = getattr(agent, "model", None)
    if client is None or not model:
        raise RuntimeError("LLM client or model not configured")

    evidence = (search_results or "").strip()
    if len(evidence) > 12000:
        evidence = evidence[:11800] + "\n…"

    system = (
        "You are Holix, a research analyst. Use ONLY the web search evidence below. "
        "Respond in Russian with a structured Markdown analysis: section titles in **bold**, "
        "bullet lists with -, key terms in **bold**. Cover key findings, pros/cons, risks, "
        "and a clear recommendation. Do NOT output only a list of links — synthesize insights. "
        "If evidence is insufficient, state limitations explicitly."
    )
    user = (
        f"Поисковый запрос: {search_query}\n\n"
        f"Задание пользователя: {analysis_instruction or user_message}\n\n"
        f"Результаты web_search:\n{evidence}\n\n"
        "Дай развёрнутый анализ и практическую рекомендацию."
    )

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.35,
    )
    content = response.choices[0].message.content
    return (content or "").strip() or "Не удалось сформировать анализ."


async def _run_tool(
    host: Any,
    agent: Any,
    conversation_id: str,
    tool_name: str,
    args: dict[str, Any],
    *,
    preview_to_chat: bool = True,
) -> tuple[bool, str]:
    from core.agent_events import ToolCallResultEvent, ToolCallStartEvent

    registry = agent.tools
    tool = registry.tools.get(tool_name)
    if tool is None:
        return True, f"✗ Tool `{tool_name}` не найден."

    args_raw = json.dumps(args, ensure_ascii=False)
    detail = str(args.get("query") or args.get("task") or args.get("job_id") or "")[:200]

    await host._send_text(f"🔧 {tool_name}" + (f": {detail}" if detail else ""))

    agent.emit(
        ToolCallStartEvent(
            tool_name=tool_name,
            tool_id="max-direct",
            arguments_raw=args_raw,
            conversation_id=conversation_id,
        )
    )

    started = time.monotonic()
    try:
        from core.tools.execution_context import conversation_scope, reset_conversation_scope

        token = conversation_scope(conversation_id)
        try:
            if registry._action_guard:
                result = await registry._action_guard.check_and_execute(
                    tool_name=tool_name,
                    tool_instance=tool,
                    arguments=args,
                    execute_fn=tool.execute,
                    conversation_id=conversation_id,
                )
            else:
                result = await tool.execute(**args)
        finally:
            reset_conversation_scope(token)
    except Exception as exc:
        result = f"Error executing {tool_name}: {exc}"
        logger.exception("MAX direct tool %s failed", tool_name)

    duration_ms = (time.monotonic() - started) * 1000.0
    body = str(result or "")
    agent.emit(
        ToolCallResultEvent(
            tool_name=tool_name,
            tool_id="max-direct",
            result=body,
            duration_ms=duration_ms,
            conversation_id=conversation_id,
            truncated=len(body) > 200,
        )
    )

    logger.info("MAX direct tool done (%s, %d chars)", tool_name, len(body))
    if not preview_to_chat:
        return True, body
    preview = _format_tool_preview(tool_name, body)
    return True, preview


def _format_tool_preview(tool_name: str, body: str) -> str:
    from integrations.max.subagent_format import format_list_subagents_result

    if tool_name == "list_subagents":
        return format_list_subagents_result(body)
    preview = body if len(body) <= 3500 else body[:3480] + "…"
    return f"📋 {tool_name}\n{preview}"