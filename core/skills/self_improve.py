"""Post-session skill proposals (staging, not live writes)."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

logger = logging.getLogger(__name__)


async def maybe_propose_skill(
    agent: Any,
    conversation_id: str,
    messages: list[dict[str, Any]],
    final_response: str,
) -> dict[str, Any] | None:
    """Analyze a finished session and stage a skill proposal when warranted."""
    skills = getattr(agent, "skills", None)
    if skills is None:
        return None
    try:
        should_create = await skills.should_create_skill(messages, final_response)
    except Exception as exc:
        logger.warning("should_create_skill failed: %s", exc)
        return None
    if not should_create:
        return None

    user_messages = [m for m in messages if m.get("role") == "user"]
    if not user_messages:
        return None
    task_description = str(user_messages[0].get("content") or "")

    from core.agent_events import (
        SelfImprovementStartedEvent,
        SkillProposalRejectedEvent,
    )
    from core.skills.dedup import find_duplicate_skill, looks_like_junk_skill
    from core.skills.generator import SkillGenerator
    from core.skills.proposal import SkillProposalStore, is_protected_skill

    if callable(getattr(agent, "emit", None)):
        agent.emit(
            SelfImprovementStartedEvent(
                conversation_id=conversation_id,
                task_description=task_description[:200],
            )
        )

    existing_names: list[str] = []
    try:
        if not skills.all_skills:
            skills.load_all_skills(defer_index=True)
        existing_names = sorted(skills.all_skills.keys())
    except Exception:
        existing_names = []

    from core.skills.lifecycle import resolve_skill_locale

    profile = str(
        getattr(getattr(agent, "config", None), "profile_name", None)
        or getattr(agent, "profile_name", None)
        or "default"
    )
    locale = resolve_skill_locale(profile)
    try:
        generator = SkillGenerator(agent.client, model=agent.model)
        skill_data = await generator.create_skill_from_session(
            messages,
            task_description,
            existing_names=existing_names,
            locale=locale,
        )
    except Exception as exc:
        logger.warning("skill generator failed: %s", exc)
        return None

    if not skill_data or not skill_data.get("name"):
        return None

    name = str(skill_data.get("name") or "")
    description = str(skill_data.get("description") or "")
    tags = list(skill_data.get("tags") or [])
    action = str(skill_data.get("action") or "create").strip().lower()
    refuse_reason = str(skill_data.get("refuse_reason") or "")

    if action == "refuse" or looks_like_junk_skill(name=name, description=description, tags=tags):
        _record_refuse(agent, name, refuse_reason or "junk")
        if callable(getattr(agent, "emit", None)):
            agent.emit(
                SkillProposalRejectedEvent(
                    skill_name=name,
                    reason=refuse_reason or "junk",
                    conversation_id=conversation_id,
                )
            )
        return None

    dup = find_duplicate_skill(
        skills.all_skills,
        name=name,
        description=description,
    )
    if dup and is_protected_skill(dup, str(dup.get("name") or "")):
        if callable(getattr(agent, "emit", None)):
            agent.emit(
                SkillProposalRejectedEvent(
                    skill_name=str(dup.get("name") or name),
                    reason="protected",
                    conversation_id=conversation_id,
                )
            )
        return None
    if action == "reuse" or (dup and action != "patch"):
        if action == "reuse" or (dup and not skill_data.get("content")):
            if callable(getattr(agent, "emit", None)):
                agent.emit(
                    SkillProposalRejectedEvent(
                        skill_name=str((dup or {}).get("name") or name),
                        reason="already_covered",
                        conversation_id=conversation_id,
                    )
                )
            return None
        action = "patch"
        name = str(dup.get("name") or name)

    if action == "patch" and not dup:
        dup = skills.all_skills.get(name)
        if not dup:
            action = "create"

    content = str(skill_data.get("content") or "").strip()
    if not content:
        if callable(getattr(agent, "emit", None)):
            agent.emit(
                SkillProposalRejectedEvent(
                    skill_name=name,
                    reason="empty",
                    conversation_id=conversation_id,
                )
            )
        return None

    from core.skills.lifecycle import settle_proposal

    store = SkillProposalStore(skills.skills_dir)
    try:
        rec = store.stage(
            name=name,
            action=action,
            content=content,
            description=description,
            tags=tags,
            examples=list(skill_data.get("examples") or []),
            target_name=str((dup or {}).get("name") or name),
            origin="session",
            source_session=conversation_id,
            source_run=str(getattr(agent, "run_id", "") or ""),
            agent_slot=str(getattr(agent, "agent_slot", "main") or "main"),
            reason="session_self_improve",
            duplicate_of=(str(dup.get("name")) if dup else None),
            quality_score=int(skill_data.get("quality_score") or 0),
            locale=locale,
        )
        rec = settle_proposal(
            store,
            rec,
            manager=skills,
            profile=profile,
            agent=agent,
            skill_data=skill_data,
        )
    except Exception as exc:
        logger.warning("failed to stage skill proposal: %s", exc)
        if callable(getattr(agent, "emit", None)):
            agent.emit(
                SkillProposalRejectedEvent(
                    skill_name=name,
                    reason=str(exc),
                    conversation_id=conversation_id,
                )
            )
        return None

    return rec


def _record_refuse(agent: Any, name: str, reason: str) -> None:
    if reason not in {"junk", "transient_failure"}:
        return
    skills = getattr(agent, "skills", None)
    if skills is None:
        return
    try:
        from core.achievements.engine import record_skill_signal

        record_skill_signal(
            skills.skills_dir,
            "refused",
            evidence={"skill_name": name, "reason": reason},
        )
    except Exception:
        return


async def maybe_propose_skill_from_subagent(
    *,
    skills: Any,
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    final_response: str,
    conversation_id: str,
    profile: str = "default",
    agent_slot: str = "main",
    emit: Any | None = None,
    run_id: str = "",
    config: Any | None = None,
) -> dict[str, Any] | None:
    """Same pending/quality path as main, for a finished sub-agent job."""
    if skills is None or client is None or not (model or "").strip():
        return None
    proxy = SimpleNamespace(
        skills=skills,
        client=client,
        model=model,
        config=config or SimpleNamespace(profile_name=profile),
        profile_name=profile,
        agent_slot=agent_slot or "main",
        run_id=run_id,
        emit=emit,
    )
    return await maybe_propose_skill(proxy, conversation_id, messages, final_response)
