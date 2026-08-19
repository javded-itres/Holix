"""Approve/reject a pending skill by profile + proposal id/suffix."""

from __future__ import annotations

from typing import Any

from core.i18n import t
from core.skills.lifecycle import apply_skill_decision, find_proposal_by_suffix


def manager_for_profile(profile: str):
    from core.di import resolve_runtime_config
    from core.profile import ProfileManager
    from core.skills.manager import SkillsManager

    mgr_p = ProfileManager()
    name = (profile or "default").strip() or "default"
    if mgr_p.profile_exists(name):
        cfg = mgr_p.load_profile(name)
        runtime = resolve_runtime_config(cfg)
    else:
        runtime = resolve_runtime_config()
    skills = SkillsManager(runtime)
    skills.load_all_skills(defer_index=True)
    return skills


def decide_skill_proposal(
    profile: str,
    proposal_token: str,
    *,
    approve: bool,
    locale: str | None = None,
) -> dict[str, Any]:
    skills = manager_for_profile(profile)
    store_dir = skills.skills_dir
    from core.skills.proposal import SkillProposalStore

    store = SkillProposalStore(store_dir)
    rec = store.get(proposal_token) or find_proposal_by_suffix(store, proposal_token)
    if not rec:
        return {"ok": False, "message": t("skill.cb.missing", locale)}
    try:
        out = apply_skill_decision(
            store,
            str(rec["id"]),
            approve=approve,
            manager=skills if approve else None,
        )
    except Exception as exc:
        return {"ok": False, "message": t("skill.cb.error", locale, error=str(exc))}
    key = "skill.cb.approved" if approve else "skill.cb.rejected"
    return {"ok": True, "message": t(key, locale), "proposal": out}
