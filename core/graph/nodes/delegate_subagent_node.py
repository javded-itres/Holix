"""Delegate plan steps to sub-agents when configured."""

from __future__ import annotations

import logging
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from core.graph.state import HelixGraphState, get_agent_from_config

logger = logging.getLogger(__name__)


async def delegate_subagent_node(
    state: HelixGraphState,
    config: RunnableConfig,
) -> Dict[str, Any]:
    """Spawn a sub-agent for the current plan step when ``subagent_type`` is set.

    When sub-agents are disabled or no type is specified, passes through to react.
    """
    agent = get_agent_from_config(config)
    if not agent:
        return {}

    cfg = getattr(agent, "config", None)
    if not cfg or not cfg.enable_subagents:
        return {}

    plan_steps = state.get("plan_steps", [])
    current_step_idx = state.get("current_plan_step", 0)
    if current_step_idx >= len(plan_steps):
        return {}

    step = plan_steps[current_step_idx]
    subagent_type = step.get("subagent_type")
    if not subagent_type:
        return {}

    task = step.get("description", "")
    if not task:
        return {}

    try:
        manager = agent.subagents
        handle, _ = await manager.spawn_typed(subagent_type, task, wait=False)

        tasks = list(state.get("sub_agent_tasks", []))
        tasks.append(
            {
                "type": subagent_type,
                "task": task,
                "handle": handle.name,
                "process_mode": handle.config.process_mode.value,
            }
        )

        return {
            "sub_agent_tasks": tasks,
            "pending_subagent": handle.name,
            "is_step_complete": False,
        }
    except KeyError:
        logger.warning("Unknown subagent_type: %s", subagent_type)
        return {}
    except Exception as exc:
        logger.warning("Sub-agent delegation failed: %s", exc)
        return {}