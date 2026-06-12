"""Wait for pending sub-agents and inject aggregated results for react synthesis."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from core.graph.state import HolixGraphState, get_agent_from_config
from core.logging.events import log_subagent_event
from core.subagents.orchestrator import (
    OrchestrationPlan,
    SubagentTask,
    format_wave_aggregate,
)

logger = logging.getLogger(__name__)


async def _wait_job(manager, job_id: str, timeout: float) -> dict[str, Any]:
    try:
        result = await manager.wait_for(job_id, timeout=timeout)
        return {
            "success": result.success if result else False,
            "response": result.response if result else "",
            "error": result.error if result else None,
        }
    except Exception as exc:
        return {"success": False, "response": "", "error": str(exc)}


async def collect_subagent_node(
    state: HolixGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Wait for active sub-agent wave and append synthesis context to messages."""
    pending = list(state.get("pending_subagents") or [])
    legacy = state.get("pending_subagent")
    if legacy and legacy not in pending:
        pending.append(legacy)
    if not pending:
        return {}

    agent = get_agent_from_config(config)
    if not agent:
        return {"pending_subagents": [], "pending_subagent": None}

    manager = agent.subagents
    wave_idx = int(state.get("current_subagent_wave", 0))
    task_meta_raw = dict(state.get("subagent_task_meta") or {})

    timeouts = []
    for job_id in pending:
        handle = manager.get_handle(job_id)
        timeouts.append(handle.config.timeout if handle else 120.0)
    timeout = max(timeouts) if timeouts else 120.0

    try:
        payloads = await asyncio.gather(
            *[_wait_job(manager, job_id, timeout) for job_id in pending]
        )
        results = {job_id: payload for job_id, payload in zip(pending, payloads, strict=True)}

        task_meta: dict[str, SubagentTask] = {}
        step_indices: list[int] = []
        for job_id, meta in task_meta_raw.items():
            if job_id not in results:
                continue
            task_meta[job_id] = SubagentTask(
                agent_type=str(meta.get("agent_type", "")),
                task=str(meta.get("task", "")),
                step_ref=int(meta.get("step_ref", 0)),
                step_index=int(meta.get("step_index", 0)),
            )
            step_indices.append(int(meta.get("step_index", 0)))

        orch_raw = state.get("subagent_orchestration")
        total_waves = 1
        if orch_raw:
            total_waves = len(OrchestrationPlan.from_dict(orch_raw).waves) or 1

        aggregate = format_wave_aggregate(
            wave_id=wave_idx,
            total_waves=total_waves,
            results=results,
            task_meta=task_meta,
        )

        sub_results = dict(state.get("sub_agent_results", {}))
        for job_id, payload in results.items():
            sub_results[job_id] = payload

        wave_results = dict(state.get("subagent_wave_results", {}))
        wave_results[str(wave_idx)] = results

        messages = list(state.get("messages", []))
        messages.append({"role": "user", "content": aggregate})

        completed = sum(1 for p in results.values() if p.get("success"))
        log_subagent_event(
            "INFO",
            f"wave {wave_idx + 1}/{total_waves} collected {completed}/{len(results)}",
            subagent=",".join(pending),
        )
        if agent and hasattr(agent, "emit"):
            from core.agent_events import SubAgentWaveCompletedEvent

            agent.emit(
                SubAgentWaveCompletedEvent(
                    wave_id=wave_idx,
                    total_waves=total_waves,
                    completed=completed,
                    total=len(results),
                    conversation_id=state.get("conversation_id", "default"),
                )
            )

        return {
            "pending_subagents": [],
            "pending_subagent": None,
            "current_subagent_wave": wave_idx + 1,
            "sub_agent_results": sub_results,
            "subagent_wave_results": wave_results,
            "messages": messages,
            "is_step_complete": False,
            "subagent_wave_step_indices": sorted(set(step_indices)),
            "subagent_awaiting_synthesis": True,
        }
    except Exception as exc:
        logger.warning("collect_subagent failed: %s", exc)
        messages = list(state.get("messages", []))
        messages.append(
            {
                "role": "user",
                "content": (
                    f"[Sub-agents wave {wave_idx + 1} failed]\n"
                    f"success=false\n\n{exc}\n\n"
                    "Explain the failure to the user and suggest next steps."
                ),
            }
        )
        return {
            "pending_subagents": [],
            "pending_subagent": None,
            "current_subagent_wave": wave_idx + 1,
            "messages": messages,
            "is_step_complete": False,
            "subagent_awaiting_synthesis": True,
            "subagent_wave_step_indices": [],
        }