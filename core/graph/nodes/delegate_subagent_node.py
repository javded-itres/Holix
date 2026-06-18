"""Delegate plan steps to sub-agents (single or orchestrated waves)."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from core.graph.state import HolixGraphState, get_agent_from_config
from core.logging.events import log_subagent_event
from core.subagents.orchestrator import (
    OrchestrationPlan,
    build_orchestration_plan,
    current_wave,
)
from core.subagents.spawn import prepare_subagent_config

logger = logging.getLogger(__name__)


def _resolve_orchestration(
    state: HolixGraphState,
    *,
    enable_subagents: bool,
    max_concurrent: int,
    profile: str | None = None,
) -> OrchestrationPlan | None:
    raw = state.get("subagent_orchestration")
    if raw:
        return OrchestrationPlan.from_dict(raw)

    plan = build_orchestration_plan(
        plan_analysis=state.get("plan_analysis"),
        plan_steps=state.get("plan_steps", []),
        current_step_index=state.get("current_plan_step", 0),
        enable_subagents=enable_subagents,
        max_concurrent=max_concurrent,
        profile=profile,
    )
    if not plan.enabled:
        return None
    return plan


async def delegate_subagent_node(
    state: HolixGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Spawn sub-agent(s) for the current orchestration wave."""
    agent = get_agent_from_config(config)
    if not agent:
        return {}

    cfg = getattr(agent, "config", None)
    from core.config_utils import is_subagents_enabled

    if not is_subagents_enabled(cfg):
        return {}

    from core.profile.soul import profile_name_from_agent

    orchestration = _resolve_orchestration(
        state,
        enable_subagents=True,
        max_concurrent=int(getattr(cfg, "subagent_max_concurrent", 4) or 4),
        profile=profile_name_from_agent(agent),
    )
    if orchestration is None:
        return {"subagent_delegate_next": False}

    wave_idx = int(state.get("current_subagent_wave", 0))
    wave = current_wave(orchestration, wave_idx)
    if wave is None:
        return {"subagent_delegate_next": False}

    manager = agent.subagents
    pending: list[str] = []
    task_meta: dict[str, dict[str, Any]] = {}
    tasks_log = list(state.get("sub_agent_tasks", []))

    try:
        for task in wave.tasks:
            instance = manager.allocate_name(task.agent_type)
            sub_cfg = prepare_subagent_config(
                task.agent_type,
                cfg,
                instance_name=instance,
            )
            handle = await manager.spawn_sub_agent(
                sub_cfg,
                task.task,
                agent_type=task.agent_type,
            )
            pending.append(handle.name)
            task_meta[handle.name] = {
                "agent_type": task.agent_type,
                "task": task.task,
                "step_ref": task.step_ref,
                "step_index": task.step_index,
            }
            tasks_log.append(
                {
                    "type": task.agent_type,
                    "task": task.task,
                    "handle": handle.name,
                    "process_mode": handle.config.process_mode.value,
                    "wave_id": wave.wave_id,
                }
            )

        log_subagent_event(
            "INFO",
            f"wave {wave.wave_id + 1}/{len(orchestration.waves)} started",
            subagent=",".join(pending),
            task_count=len(pending),
        )
        if agent and hasattr(agent, "emit"):
            from core.agent_events import SubAgentWaveStartedEvent

            agent.emit(
                SubAgentWaveStartedEvent(
                    wave_id=wave.wave_id,
                    total_waves=len(orchestration.waves),
                    job_ids=pending,
                    conversation_id=state.get("conversation_id", "default"),
                )
            )

        return {
            "subagent_orchestration": orchestration.to_dict(),
            "current_subagent_wave": wave_idx,
            "pending_subagents": pending,
            "pending_subagent": pending[0] if len(pending) == 1 else None,
            "subagent_task_meta": task_meta,
            "sub_agent_tasks": tasks_log,
            "subagent_delegate_next": False,
            "is_step_complete": False,
        }
    except Exception as exc:
        logger.warning("Sub-agent wave delegation failed: %s", exc)
        return {"subagent_delegate_next": False}