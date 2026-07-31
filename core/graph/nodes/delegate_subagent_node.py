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


async def _spawn_task_list(
    *,
    agent: Any,
    cfg: Any,
    tasks: list[Any],
    wave_id: int,
    tasks_log: list[dict[str, Any]],
    label: str,
) -> tuple[list[str], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Spawn a list of SubagentTask-like objects (or rework dicts)."""
    manager = agent.subagents
    pending: list[str] = []
    task_meta: dict[str, dict[str, Any]] = {}

    for task in tasks:
        prior_job = ""
        if isinstance(task, dict):
            agent_type = str(task.get("agent_type") or "coder")
            task_text = str(task.get("task") or "")
            step_ref = int(task.get("step_ref") or 0)
            step_index = int(task.get("step_index") or 0)
            prior_job = str(task.get("prior_job") or "")
        else:
            agent_type = task.agent_type
            task_text = task.task
            step_ref = task.step_ref
            step_index = task.step_index

        instance = manager.allocate_name(agent_type)
        sub_cfg = prepare_subagent_config(
            agent_type,
            cfg,
            instance_name=instance,
        )
        handle = await manager.spawn_sub_agent(
            sub_cfg,
            task_text,
            agent_type=agent_type,
        )
        pending.append(handle.name)
        meta_entry: dict[str, Any] = {
            "agent_type": agent_type,
            "task": task_text,
            "step_ref": step_ref,
            "step_index": step_index,
        }
        if prior_job:
            meta_entry["prior_job"] = prior_job
        task_meta[handle.name] = meta_entry
        tasks_log.append(
            {
                "type": agent_type,
                "task": task_text[:500],
                "handle": handle.name,
                "process_mode": handle.config.process_mode.value,
                "wave_id": wave_id,
                "label": label,
            }
        )
    return pending, task_meta, tasks_log


async def delegate_subagent_node(
    state: HolixGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Spawn sub-agent(s) for the current orchestration wave or supervisor rework."""
    agent = get_agent_from_config(config)
    if not agent:
        return {}

    cfg = getattr(agent, "config", None)
    from core.config_utils import is_subagents_enabled

    if not is_subagents_enabled(cfg):
        return {}

    from core.profile.soul import profile_name_from_agent

    tasks_log = list(state.get("sub_agent_tasks", []))
    rework = list(state.get("supervisor_rework_tasks") or [])

    # --- Graph supervisor rework path (same agent types, guided tasks) ---
    if rework and state.get("supervisor_needs_rework"):
        try:
            # Keep wave index stable for collect (collect will +1 again).
            # Rework results land under current_subagent_wave before collect bumps.
            wave_idx = max(0, int(state.get("current_subagent_wave", 1) or 1) - 1)
            pending, new_meta, tasks_log = await _spawn_task_list(
                agent=agent,
                cfg=cfg,
                tasks=rework,
                wave_id=wave_idx,
                tasks_log=tasks_log,
                label="supervisor_rework",
            )
            # Preserve meta for successful jobs from the same wave (not re-run)
            task_meta = dict(state.get("subagent_task_meta") or {})
            for job_id, meta in new_meta.items():
                prior = str(meta.get("prior_job") or "")
                if prior:
                    task_meta.pop(prior, None)
                task_meta[job_id] = meta
            log_subagent_event(
                "INFO",
                f"supervisor rework started ({len(pending)} job(s))",
                subagent=",".join(pending),
                task_count=len(pending),
            )
            return {
                "pending_subagents": pending,
                "pending_subagent": pending[0] if len(pending) == 1 else None,
                "subagent_task_meta": task_meta,
                "sub_agent_tasks": tasks_log,
                "subagent_delegate_next": False,
                "is_step_complete": False,
                "supervisor_needs_rework": False,
                "supervisor_rework_tasks": [],
                # Roll wave index back so collect stores under the same wave slot
                "current_subagent_wave": wave_idx,
            }
        except Exception as exc:
            logger.warning("Supervisor rework delegation failed: %s", exc)
            return {
                "subagent_delegate_next": False,
                "supervisor_needs_rework": False,
                "supervisor_rework_tasks": [],
            }

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

    try:
        pending, task_meta, tasks_log = await _spawn_task_list(
            agent=agent,
            cfg=cfg,
            tasks=list(wave.tasks),
            wave_id=wave.wave_id,
            tasks_log=tasks_log,
            label="wave",
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
            "supervisor_needs_rework": False,
            "supervisor_rework_tasks": [],
        }
    except Exception as exc:
        logger.warning("Sub-agent wave delegation failed: %s", exc)
        return {"subagent_delegate_next": False}