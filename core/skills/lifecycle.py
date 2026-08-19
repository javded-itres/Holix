"""Settle a staged skill: score, optional auto-approve, notify all surfaces."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.i18n import t
from core.i18n.locale import LocaleStore, normalize_locale
from core.plugins.hooks import notify_hooks
from core.skills.quality import (
    clamp_score,
    heuristic_quality,
    score_tier,
    should_auto_approve,
)

logger = logging.getLogger(__name__)


def resolve_skill_locale(profile: str | None) -> str:
    name = (profile or "").strip() or "default"
    try:
        return normalize_locale(LocaleStore(name).get())
    except Exception:
        return "en"


def attach_quality(rec: dict[str, Any], skill_data: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = rec.get("quality_score")
    if raw in (None, "", 0):
        rec["quality_score"] = heuristic_quality(skill_data or rec)
    else:
        rec["quality_score"] = clamp_score(raw)
    rec["tier"] = score_tier(int(rec["quality_score"]))
    return rec


def find_proposal_by_suffix(store: Any, suffix: str) -> dict[str, Any] | None:
    token = (suffix or "").strip().lower()
    if len(token) < 4:
        return None
    for rec in store.list_pending():
        pid = str(rec.get("id") or "")
        if pid.lower().endswith(token) or pid.lower() == token:
            return rec
    return None


def apply_skill_decision(
    skills_dir: str | Any,
    proposal_id: str,
    *,
    approve: bool,
    manager: Any | None = None,
    reason: str = "",
) -> dict[str, Any]:
    from core.skills.proposal import SkillProposalStore

    store = skills_dir if hasattr(skills_dir, "approve") else SkillProposalStore(skills_dir)
    rec = store.get(proposal_id) or find_proposal_by_suffix(store, proposal_id)
    if not rec:
        raise FileNotFoundError(proposal_id)
    pid = str(rec["id"])
    if approve:
        if manager is None:
            raise ValueError("manager required to approve")
        out = store.approve(pid, manager=manager)
    else:
        out = store.reject(pid, reason=reason or "user")
    out["quality_score"] = rec.get("quality_score") or out.get("quality_score") or 0
    out["tier"] = score_tier(int(out["quality_score"] or 0))
    return out


def announce_skill_proposal(
    *,
    profile: str,
    rec: dict[str, Any],
    agent: Any | None = None,
) -> dict[str, Any]:
    """Notify Studio / Telegram / MAX. Never raises."""
    locale = rec.get("locale") or resolve_skill_locale(profile)
    score = clamp_score(rec.get("quality_score"))
    tier = rec.get("tier") or score_tier(score)
    auto = bool(rec.get("auto_applied"))
    payload = {
        "profile": profile,
        "proposal_id": rec.get("id") or "",
        "name": rec.get("name") or "",
        "description": rec.get("description") or "",
        "action": rec.get("action") or "create",
        "quality_score": score,
        "tier": tier,
        "auto_applied": auto,
        "locale": locale,
        "settings_path": "/studio/settings?tab=profile&sub=skills",
    }
    if agent is not None and hasattr(agent, "emit"):
        try:
            from core.agent_events import SkillApprovedEvent, SkillProposedEvent

            if auto:
                agent.emit(
                    SkillApprovedEvent(
                        skill_name=str(payload["name"]),
                        proposal_id=str(payload["proposal_id"]),
                        filepath=str(rec.get("filepath") or ""),
                        action=str(payload["action"]),
                        conversation_id=str(rec.get("source_session") or ""),
                    )
                )
            agent.emit(
                SkillProposedEvent(
                    skill_name=str(payload["name"]),
                    description=str(payload["description"]),
                    proposal_id=str(payload["proposal_id"]),
                    action=str(payload["action"]),
                    filepath=str(rec.get("filepath") or ""),
                    conversation_id=str(rec.get("source_session") or ""),
                    quality_score=int(payload.get("quality_score") or 0),
                    auto_applied=bool(payload.get("auto_applied")),
                )
            )
        except Exception:
            logger.debug("skill notice agent emit failed", exc_info=True)
    for fn in list(notify_hooks.skill_notice_listeners):
        try:
            result = fn(payload)
            if asyncio.iscoroutine(result):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(result)
                except RuntimeError:
                    logger.debug("no running loop for skill notice listener")
        except Exception:
            logger.warning("skill notice listener failed", exc_info=True)
    return payload


def settle_proposal(
    store: Any,
    rec: dict[str, Any],
    *,
    manager: Any,
    profile: str,
    agent: Any | None = None,
    skill_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist score, auto-approve gold+, announce everywhere."""
    attach_quality(rec, skill_data)
    rec["locale"] = rec.get("locale") or resolve_skill_locale(profile)
    # Persist score/locale onto the pending record if still staged.
    pending = store.get(str(rec.get("id") or ""))
    if pending and pending.get("status") == "pending":
        pending["quality_score"] = rec["quality_score"]
        pending["locale"] = rec["locale"]
        pending["tier"] = rec["tier"]
        store._save(pending)
        rec = pending
    rec["auto_applied"] = False
    if should_auto_approve(int(rec["quality_score"])) and rec.get("action") != "reuse":
        try:
            applied = store.approve(str(rec["id"]), manager=manager)
            applied["quality_score"] = rec["quality_score"]
            applied["tier"] = rec["tier"]
            applied["locale"] = rec["locale"]
            applied["auto_applied"] = True
            applied["description"] = rec.get("description") or applied.get("description")
            rec = applied
        except Exception:
            logger.warning("auto-approve failed for %s", rec.get("id"), exc_info=True)
            rec["auto_applied"] = False
    announce_skill_proposal(profile=profile, rec=rec, agent=agent)
    return rec


def format_skill_notice_text(payload: dict[str, Any]) -> str:
    loc = str(payload.get("locale") or "en")
    tier = payload.get("tier") or score_tier(int(payload.get("quality_score") or 0))
    label = tier.get("label_ru") if loc.startswith("ru") else tier.get("label_en")
    hint = tier.get("hint_ru") if loc.startswith("ru") else tier.get("hint_en")
    name = payload.get("name") or ""
    desc = payload.get("description") or ""
    score = int(payload.get("quality_score") or 0)
    if payload.get("auto_applied"):
        title = t("skill.notice.auto", loc, name=name)
    else:
        title = t("skill.notice.pending", loc, name=name)
    lines = [
        title,
        t("skill.notice.score", loc, score=score, tier=label, hint=hint),
    ]
    if desc:
        lines.append(desc)
    if not payload.get("auto_applied"):
        lines.append(t("skill.notice.actions", loc))
    return "\n".join(lines)
