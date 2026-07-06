"""Auto-delegate web research tasks to the web_researcher sub-agent."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from core.config_utils import is_subagents_enabled
from core.direct_dispatch.search_intent import is_web_research_request

logger = logging.getLogger(__name__)

NotifyFn = Callable[[str], Awaitable[None]]


async def try_web_research_subagent_dispatch(
    agent: Any,
    message: str,
    *,
    timeout_seconds: float = 600.0,
    notify: NotifyFn | None = None,
    wait_for_result: bool = True,
) -> tuple[bool, str]:
    """Spawn web_researcher; optionally wait and return (handled, reply_or_job_id)."""
    text = (message or "").strip()
    if not text or not is_web_research_request(text):
        return False, ""

    if not is_subagents_enabled(getattr(agent, "config", None)):
        return False, ""

    mgr = getattr(agent, "subagents", None)
    if mgr is None:
        return False, ""

    from core.tools.subagents import DelegateToSubAgentTool, WaitSubAgentResultTool

    logger.info("Direct dispatch: web_researcher sub-agent (%r)", text[:80])

    delegate = DelegateToSubAgentTool(agent)
    wait = WaitSubAgentResultTool(agent)

    spawned_raw = await delegate.execute(agent_type="web_researcher", task=text)
    if spawned_raw.startswith("Error"):
        return True, spawned_raw

    try:
        spawned = json.loads(spawned_raw)
    except json.JSONDecodeError:
        return True, f"Не удалось разобрать ответ delegate_to_subagent: {spawned_raw[:500]}"

    job_id = spawned.get("job_id")
    if not job_id:
        return True, f"Субагент не запущен: {spawned.get('message') or spawned_raw}"

    if notify is not None:
        from core.presenters.subagent_tool_text import format_subagent_tool_notice

        notice = format_subagent_tool_notice("delegate_to_subagent", spawned_raw)
        if notice:
            await notify(notice)
        else:
            await notify("🔍 Запускаю субагента **web_researcher**…")

    if not wait_for_result:
        return True, job_id

    result_raw = await wait.execute(job_id=job_id, timeout_seconds=timeout_seconds)
    if result_raw.startswith("Error"):
        return True, result_raw

    try:
        result = json.loads(result_raw)
    except json.JSONDecodeError:
        return True, result_raw

    if result.get("success"):
        body = (result.get("response") or "").strip()
        if body:
            return True, body
        return True, "Субагент web_researcher завершил работу без текстового ответа."

    err = (result.get("error") or "unknown error").strip()
    return True, f"Субагент web_researcher завершился с ошибкой: {err}"