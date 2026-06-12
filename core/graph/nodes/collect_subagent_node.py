"""Wait for a pending sub-agent and inject its result into the conversation."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from core.graph.state import HolixGraphState, get_agent_from_config

logger = logging.getLogger(__name__)


async def collect_subagent_node(
    state: HolixGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Wait for ``pending_subagent`` (spawned earlier) and append result to messages."""
    pending = state.get("pending_subagent")
    if not pending:
        return {}

    agent = get_agent_from_config(config)
    if not agent:
        return {"pending_subagent": None}

    manager = agent.subagents
    handle = manager.get_handle(pending)
    if not handle:
        return {"pending_subagent": None}

    try:
        result = await manager.wait_for(pending, timeout=handle.config.timeout)
        results = dict(state.get("sub_agent_results", {}))
        results[pending] = {
            "response": result.response if result else "",
            "success": result.success if result else False,
            "error": result.error if result else None,
        }
        messages = list(state.get("messages", []))
        snippet = (result.response or result.error or "")[:4000] if result else ""
        messages.append(
            {
                "role": "user",
                "content": (
                    f"[Sub-agent '{pending}' completed]\n"
                    f"success={result.success if result else False}\n\n{snippet}"
                ),
            }
        )
        return {
            "pending_subagent": None,
            "sub_agent_results": results,
            "messages": messages,
            "is_step_complete": True,
        }
    except Exception as exc:
        logger.warning("collect_subagent failed for %s: %s", pending, exc)
        return {"pending_subagent": None}