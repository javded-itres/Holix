"""Graph-native supervisor node — post-wave diagnosis and rework cycle.

Runs after ``collect_subagent`` in plan_and_execute. Looks at the wave just
collected; if jobs failed or look thrashy, schedules **rework on the same
agent types** with guidance (same orchestration cycle, not a new plan).

Mid-run guidance still comes from the asyncio ``SubagentSupervisor`` sidecar;
this node owns the **graph-level** rework loop:

  collect → supervisor → (rework? delegate : react)
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from core.graph.state import HolixGraphState, get_agent_from_config

logger = logging.getLogger(__name__)

_DEFAULT_MAX_REWORK = 2


def _max_rework_rounds(agent: Any) -> int:
    cfg = getattr(agent, "config", None) if agent else None
    if cfg is None:
        return _DEFAULT_MAX_REWORK
    raw = getattr(cfg, "subagent_supervisor_max_interventions", None)
    if raw is None:
        return _DEFAULT_MAX_REWORK
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_REWORK


def _supervisor_enabled(agent: Any) -> bool:
    cfg = getattr(agent, "config", None) if agent else None
    if cfg is None:
        return True
    val = getattr(cfg, "subagent_supervisor_enabled", True)
    return True if val is None else bool(val)


def _error_looks_structural(error: str, response: str) -> bool:
    text = f"{error}\n{response}".lower()
    markers = (
        "max steps",
        "timed out",
        "timeout",
        "loop",
        "permission denied",
        "error:",
        "traceback",
        "failed",
        "cancelled",
    )
    return any(m in text for m in markers)


def _build_rework_task(
    *,
    agent_type: str,
    original_task: str,
    error: str,
    response: str,
    step_ref: int,
    step_index: int,
    prior_job: str,
) -> dict[str, Any]:
    err = (error or response or "unknown failure").strip()
    if len(err) > 800:
        err = err[:799] + "…"
    guided = (
        f"{original_task.strip()}\n\n"
        f"### Supervisor rework (same sub-agent type)\n"
        f"Previous attempt (`{prior_job}`) did not succeed.\n"
        f"**Failure signal:** {err}\n\n"
        f"**Instructions:**\n"
        f"- Do not repeat the same failing tool sequence.\n"
        f"- Fix the root cause or produce a clear partial deliverable.\n"
        f"- Prefer smaller steps: verify paths, then write/test.\n"
        f"- If blocked, state the exact blocker and what you already tried."
    )
    return {
        "agent_type": agent_type,
        "task": guided,
        "step_ref": step_ref,
        "step_index": step_index,
        "prior_job": prior_job,
        "failure": err[:400],
    }


async def supervisor_node(
    state: HolixGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Diagnose last sub-agent wave; schedule rework or pass through to synthesis."""
    agent = get_agent_from_config(config)
    if not _supervisor_enabled(agent):
        return {
            "supervisor_needs_rework": False,
            "supervisor_rework_tasks": [],
        }

    if not state.get("subagent_awaiting_synthesis"):
        # No fresh wave to inspect
        return {
            "supervisor_needs_rework": False,
            "supervisor_rework_tasks": [],
        }

    wave_idx_next = int(state.get("current_subagent_wave", 0) or 0)
    completed_wave = max(0, wave_idx_next - 1)
    wave_results = dict(state.get("subagent_wave_results") or {})
    results = wave_results.get(str(completed_wave)) or {}
    if not results:
        return {
            "supervisor_needs_rework": False,
            "supervisor_rework_tasks": [],
        }

    rework_round = int(state.get("supervisor_rework_round", 0) or 0)
    max_rounds = _max_rework_rounds(agent)
    task_meta = dict(state.get("subagent_task_meta") or {})
    log = list(state.get("supervisor_log") or [])

    failed_jobs: list[tuple[str, dict[str, Any]]] = []
    for job_id, payload in results.items():
        if not isinstance(payload, dict):
            continue
        if payload.get("success"):
            continue
        failed_jobs.append((job_id, payload))

    if not failed_jobs:
        return {
            "supervisor_needs_rework": False,
            "supervisor_rework_tasks": [],
            "supervisor_last_diagnosis": {
                "wave": completed_wave,
                "kind": "ok",
                "failed": 0,
                "total": len(results),
            },
        }

    if rework_round >= max_rounds:
        summary = (
            f"Supervisor: {len(failed_jobs)}/{len(results)} sub-agent job(s) failed "
            f"on wave {completed_wave + 1}; rework limit ({max_rounds}) reached. "
            "Synthesize best-effort from available results."
        )
        messages = list(state.get("messages") or [])
        messages.append({"role": "user", "content": f"[Supervisor]\n{summary}"})
        log.append(
            {
                "wave": completed_wave,
                "kind": "exhausted",
                "failed": len(failed_jobs),
                "round": rework_round,
            }
        )
        if agent and hasattr(agent, "emit"):
            try:
                from core.agent_events import SubAgentSupervisorEvent

                agent.emit(
                    SubAgentSupervisorEvent(
                        name="wave",
                        agent_type="supervisor",
                        kind="exhausted",
                        severity="warning",
                        attempt=rework_round,
                        max_interventions=max_rounds,
                        summary=summary,
                        message=summary,
                        exhausted=True,
                        conversation_id=str(state.get("conversation_id") or "default"),
                    )
                )
            except Exception:
                logger.debug("supervisor_node emit failed", exc_info=True)
        return {
            "messages": messages,
            "supervisor_needs_rework": False,
            "supervisor_rework_tasks": [],
            "supervisor_log": log,
            "supervisor_last_diagnosis": {
                "wave": completed_wave,
                "kind": "exhausted",
                "failed": len(failed_jobs),
                "total": len(results),
            },
        }

    rework_tasks: list[dict[str, Any]] = []
    for job_id, payload in failed_jobs:
        err = str(payload.get("error") or "")
        resp = str(payload.get("response") or "")
        if not _error_looks_structural(err, resp) and not err:
            # Soft failure with empty body — still rework once
            pass
        meta = task_meta.get(job_id) or {}
        agent_type = str(meta.get("agent_type") or job_id.split("-")[0] or "coder")
        original = str(meta.get("task") or "Continue the assigned work")
        rework_tasks.append(
            _build_rework_task(
                agent_type=agent_type,
                original_task=original,
                error=err,
                response=resp,
                step_ref=int(meta.get("step_ref") or 0),
                step_index=int(meta.get("step_index") or 0),
                prior_job=job_id,
            )
        )

    if not rework_tasks:
        return {
            "supervisor_needs_rework": False,
            "supervisor_rework_tasks": [],
        }

    summary = (
        f"Supervisor: scheduling rework for {len(rework_tasks)} failed job(s) "
        f"(round {rework_round + 1}/{max_rounds}) on wave {completed_wave + 1}."
    )
    messages = list(state.get("messages") or [])
    detail_lines = [
        f"- `{t['prior_job']}` ({t['agent_type']}): {t.get('failure', '')[:200]}"
        for t in rework_tasks
    ]
    messages.append(
        {
            "role": "user",
            "content": (
                f"[Supervisor rework]\n{summary}\n"
                + "\n".join(detail_lines)
                + "\n\nSub-agents will retry with corrected guidance before synthesis."
            ),
        }
    )
    log.append(
        {
            "wave": completed_wave,
            "kind": "rework",
            "failed": len(rework_tasks),
            "round": rework_round + 1,
            "jobs": [t["prior_job"] for t in rework_tasks],
        }
    )

    if agent and hasattr(agent, "emit"):
        try:
            from core.agent_events import SubAgentSupervisorEvent, ThinkingEvent

            agent.emit(
                SubAgentSupervisorEvent(
                    name="wave",
                    agent_type="supervisor",
                    kind="rework",
                    severity="warning",
                    attempt=rework_round + 1,
                    max_interventions=max_rounds,
                    summary=summary,
                    message=summary,
                    exhausted=False,
                    conversation_id=str(state.get("conversation_id") or "default"),
                )
            )
            agent.emit(
                ThinkingEvent(
                    message=summary,
                    conversation_id=str(state.get("conversation_id") or "default"),
                )
            )
        except Exception:
            logger.debug("supervisor_node emit failed", exc_info=True)

    logger.info(summary)

    return {
        "messages": messages,
        "supervisor_needs_rework": True,
        "supervisor_rework_tasks": rework_tasks,
        "supervisor_rework_round": rework_round + 1,
        # Keep synthesis flag false until rework collected
        "subagent_awaiting_synthesis": False,
        "supervisor_log": log,
        "supervisor_last_diagnosis": {
            "wave": completed_wave,
            "kind": "rework",
            "failed": len(rework_tasks),
            "total": len(results),
            "round": rework_round + 1,
        },
    }
