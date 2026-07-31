"""Reflexion node — verbal self-reflection after a draft answer, then optional retry.

Classic Reflexion loop (simplified for Holix):

1. Agent produces a draft (``is_final`` / end of ReAct turn)
2. MetaAgent evaluates answer (+ optional tool trajectory)
3. If quality is low → append reflection to messages, clear final, route back to react
4. Reflections are logged in state and stored to episodic LTM when available

Disabled when ``enable_self_refinement`` is false (node becomes a pass-through).
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from core.config_utils import is_self_refinement_enabled
from core.graph.state import HolixGraphState, get_agent_from_config
from core.meta_agent import MetaAgent, QualityAssessment
from core.presenters.final_content import is_aborted_final_response, is_placeholder_final

logger = logging.getLogger(__name__)


def _trajectory_summary(state: HolixGraphState, *, max_items: int = 8) -> str:
    """Compact tool/assistant trajectory for the evaluator."""
    lines: list[str] = []
    messages = list(state.get("messages") or [])
    for msg in messages[-40:]:
        role = msg.get("role")
        if role == "assistant" and msg.get("tool_calls"):
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function") if isinstance(tc, dict) else None
                if not isinstance(fn, dict):
                    fn = {}
                name = str(fn.get("name") or tc.get("name") or "?")
                args = str(fn.get("arguments") or "")[:120]
                lines.append(f"tool_call: {name}({args})")
        elif role == "tool":
            content = str(msg.get("content") or "")
            preview = content.replace("\n", " ")[:160]
            err = content.lower().startswith("error") or "traceback" in content.lower()
            tag = "tool_error" if err else "tool_result"
            lines.append(f"{tag}: {preview}")
    if not lines:
        # Fall back to last tool_results in state
        for tr in list(state.get("tool_results") or [])[-max_items:]:
            name = str(tr.get("name") or tr.get("tool_name") or "tool")
            content = str(tr.get("content") or tr.get("result") or "")[:160]
            lines.append(f"tool: {name} → {content}")
    return "\n".join(lines[-max_items:])


def _format_reflection_message(
    assessment: QualityAssessment,
    *,
    iteration: int,
    trajectory: str,
) -> str:
    areas = ", ".join(assessment.improvement_areas[:5]) if assessment.improvement_areas else "general quality"
    traj_block = ""
    if trajectory.strip():
        traj_block = f"\n### Recent trajectory (tools)\n{trajectory}\n"

    suggestion = (assessment.refinement_prompt or "").strip() or (
        "Revise the answer to fully address the user task with correct, concrete results."
    )
    return (
        f"## Reflexion (iteration {iteration})\n"
        f"Your previous answer was evaluated and needs improvement "
        f"(quality≈{assessment.quality_score:.2f}).\n\n"
        f"**Issues:** {areas}\n"
        f"**Reasoning:** {(assessment.reasoning or '')[:500]}\n"
        f"{traj_block}\n"
        f"### Self-reflection directive\n"
        f"{suggestion}\n\n"
        f"Produce an **improved final answer**. "
        f"Do not repeat the same incomplete claim. "
        f"Use tools if needed to verify or complete the work."
    )


async def _persist_reflection(
    agent: Any,
    *,
    conversation_id: str,
    user_input: str,
    assessment: QualityAssessment,
    iteration: int,
    will_retry: bool,
) -> None:
    memory = getattr(agent, "memory", None)
    if not memory or not hasattr(memory, "episodic"):
        return
    try:
        outcome = "retry" if will_retry else "accept"
        summary = (
            f"Reflexion #{iteration}: quality={assessment.quality_score:.2f}, "
            f"needs_refinement={assessment.needs_refinement}, outcome={outcome}, "
            f"areas={', '.join(assessment.improvement_areas[:3])}"
        )
        await memory.episodic.store_episode(
            conversation_id=conversation_id,
            summary=summary,
            outcome=outcome,
            metadata={
                "type": "reflexion",
                "iteration": iteration,
                "quality_score": assessment.quality_score,
                "improvement_areas": assessment.improvement_areas[:5],
                "original_task": (user_input or "")[:200],
                "will_retry": will_retry,
            },
        )
        if will_retry and assessment.improvement_areas and hasattr(memory, "strategic"):
            key = f"reflexion_{(assessment.improvement_areas[0] or 'general')[:40]}"
            await memory.strategic.store_strategy(
                key=key,
                content=(
                    f"When quality is low on '{assessment.improvement_areas[0]}', "
                    f"apply: {(assessment.refinement_prompt or '')[:300]}"
                ),
                category="reflexion",
                source="reflexion",
                metadata={"quality_score": assessment.quality_score},
            )
    except Exception:
        logger.debug("Failed to persist reflexion episode", exc_info=True)


async def reflect_node(state: HolixGraphState, config: RunnableConfig) -> dict[str, Any]:
    """Evaluate draft final answer; request another ReAct pass when needed."""
    agent = get_agent_from_config(config)
    cfg = getattr(agent, "config", None) if agent else None

    if not is_self_refinement_enabled(cfg, default=True):
        return {"needs_refinement": False}

    if str(state.get("plan_status") or "") == "rejected":
        return {"needs_refinement": False}

    final_response = str(state.get("final_response") or "").strip()
    if not final_response or is_placeholder_final(final_response) or is_aborted_final_response(
        final_response
    ):
        return {"needs_refinement": False}

    reflection_count = int(state.get("reflection_count") or state.get("refinement_iterations") or 0)
    max_iter = int(
        state.get("max_refinement_iterations")
        or getattr(cfg, "max_refinement_iterations", 2)
        or 2
    )
    if reflection_count >= max_iter:
        logger.info("Reflexion: max iterations (%s) reached", max_iter)
        return {"needs_refinement": False}

    if not agent or not hasattr(agent, "client"):
        return {"needs_refinement": False}

    user_input = str(state.get("user_input") or "")
    trajectory = _trajectory_summary(state)
    threshold = float(getattr(cfg, "refinement_quality_threshold", 0.7) or 0.7)

    meta = MetaAgent(
        client=agent.client,
        model=getattr(agent, "model", None) or "",
    )
    try:
        assessment = await meta.evaluate_response(
            response=final_response,
            original_task=user_input,
            context={
                "iteration": reflection_count,
                "execution_mode": state.get("execution_mode", "react"),
                "step_count": state.get("step_count", 0),
                "trajectory": trajectory[:2000],
                "prior_reflections": len(state.get("reflection_log") or []),
            },
        )
    except Exception as exc:
        logger.warning("Reflexion evaluate failed: %s", exc)
        return {"needs_refinement": False}

    needs = bool(assessment.needs_refinement) or float(assessment.quality_score) < threshold
    # If score is high, trust it even if needs_refinement flag is noisy
    if float(assessment.quality_score) >= max(threshold, 0.85):
        needs = False

    entry = {
        "iteration": reflection_count + 1,
        "quality_score": float(assessment.quality_score),
        "needs_refinement": needs,
        "improvement_areas": list(assessment.improvement_areas or [])[:5],
        "reasoning": (assessment.reasoning or "")[:400],
        "refinement_prompt": (assessment.refinement_prompt or "")[:400],
    }
    reflection_log = list(state.get("reflection_log") or [])
    reflection_log.append(entry)

    conversation_id = str(state.get("conversation_id") or "default")
    await _persist_reflection(
        agent,
        conversation_id=conversation_id,
        user_input=user_input,
        assessment=assessment,
        iteration=reflection_count + 1,
        will_retry=needs,
    )

    if agent and hasattr(agent, "emit"):
        try:
            from core.agent_events import ThinkingEvent

            if needs:
                agent.emit(
                    ThinkingEvent(
                        message=(
                            f"Reflexion: quality {assessment.quality_score:.2f} "
                            f"< {threshold:.2f} — retrying with self-feedback "
                            f"({reflection_count + 1}/{max_iter})"
                        ),
                        conversation_id=conversation_id,
                    )
                )
            else:
                agent.emit(
                    ThinkingEvent(
                        message=(
                            f"Reflexion: quality {assessment.quality_score:.2f} OK — finalizing"
                        ),
                        conversation_id=conversation_id,
                    )
                )
        except Exception:
            pass

    if not needs:
        logger.info(
            "Reflexion: accept answer quality=%.2f (iter=%s)",
            assessment.quality_score,
            reflection_count + 1,
        )
        return {
            "needs_refinement": False,
            "reflection_log": reflection_log,
            "refinement_iterations": reflection_count + 1,
            "reflection_count": reflection_count + 1,
        }

    reflection_msg = _format_reflection_message(
        assessment,
        iteration=reflection_count + 1,
        trajectory=trajectory,
    )
    messages = list(state.get("messages") or [])
    # Keep the draft visible as assistant content if not already last assistant
    last = messages[-1] if messages else None
    if not (
        last
        and last.get("role") == "assistant"
        and (last.get("content") or "").strip() == final_response
    ):
        messages.append({"role": "assistant", "content": final_response})
    messages.append({"role": "user", "content": reflection_msg})

    logger.info(
        "Reflexion: retry with feedback quality=%.2f areas=%s",
        assessment.quality_score,
        entry["improvement_areas"],
    )

    return {
        "messages": messages,
        "needs_refinement": True,
        "is_final": False,
        "final_response": "",
        "tool_calls": [],
        "reflection_log": reflection_log,
        "reflection_count": reflection_count + 1,
        "refinement_iterations": reflection_count + 1,
    }
