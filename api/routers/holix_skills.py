"""Holix management: skills list, search, assignments."""

from __future__ import annotations

from pathlib import Path

from core.hub.normalize import (
    discover_skill_files,
    parse_skill_file,
    resolve_skill_markdown_path,
)
from core.skills.assignments import agents_for_skill
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import verify_api_key
from api.di import ProfileManager
from api.schemas.holix import SkillAssignmentsPatchRequest
from api.services.holix_deps import load_existing_profile, profile_access

router = APIRouter(
    prefix="/api/holix/profiles/{profile_id}/skills", tags=["holix-skills"], route_class=DishkaRoute
)


class SkillPendingApproveRequest(BaseModel):
    assign: list[str] = Field(default_factory=list)


class SkillPendingMergeRequest(BaseModel):
    target: str


def _skills_manager(config):
    from core.di import resolve_runtime_config
    from core.skills.manager import SkillsManager

    mgr = SkillsManager(resolve_runtime_config(config))
    mgr.load_all_skills()
    return mgr


@router.get("")
async def list_skills(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    limit: int = Query(50, ge=1, le=500),
    agent: str | None = Query(None),
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _, config = load_existing_profile(manager, profile_id)
    mgr = _skills_manager(config)
    slot = agent or "main"
    assigns = getattr(config, "skill_assignments", None) or {}
    skills = []
    for name in sorted(mgr.all_skills.keys()):
        skill = mgr.all_skills[name]
        if agent and not mgr.is_allowed_for_agent(skill, slot):
            continue
        skills.append(
            {
                "name": name,
                "description": (skill.get("description") or "")[:200],
                "tags": skill.get("tags") or [],
                "assigned_agents": agents_for_skill(assigns, name),
            }
        )
        if len(skills) >= limit:
            break
    return {"skills": skills, "count": len(skills)}


@router.get("/search")
async def search_skills(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    q: str = Query(..., min_length=1),
    agent: str | None = Query(None),
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _, config = load_existing_profile(manager, profile_id)
    mgr = _skills_manager(config)
    results = mgr.get_relevant_skills(q, top_k=20, agent_slot=agent or "main")
    return {
        "query": q,
        "results": [
            {"name": r.get("name", ""), "description": (r.get("description") or "")[:200]}
            for r in results
        ],
        "count": len(results),
    }


@router.get("/assignments")
async def get_assignments(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _, config = load_existing_profile(manager, profile_id)
    return {"assignments": getattr(config, "skill_assignments", None) or {}}


@router.patch("/assignments")
async def patch_assignments(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    body: SkillAssignmentsPatchRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager, config = load_existing_profile(manager, profile_id)
    config.skill_assignments = body.assignments
    manager.save_profile(profile_id, config)
    return {"assignments": config.skill_assignments, "reload_required": True}


@router.post("/seed-bundled")
async def seed_bundled(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    force: bool = Query(False),
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    manager, config = load_existing_profile(manager, profile_id)
    from core.skills.bundled import ensure_bundled_assigned_to_main, seed_bundled_skills

    skills_dir = Path(config.skills_dir)
    installed = seed_bundled_skills(skills_dir, overwrite=force)
    assigns, assigned = ensure_bundled_assigned_to_main(
        getattr(config, "skill_assignments", None) or {},
        installed or None,
    )
    if assigned:
        config.skill_assignments = assigns
        manager.save_profile(profile_id, config)
    return {
        "installed": installed,
        "assigned_to_main": assigned,
        "reload_required": bool(installed or assigned),
    }


def _proposal_store(config):
    from core.skills.proposal import SkillProposalStore

    return SkillProposalStore(config.skills_dir)


def _proposal_public(rec: dict) -> dict:
    return {
        "id": rec.get("id"),
        "action": rec.get("action"),
        "status": rec.get("status"),
        "name": rec.get("name"),
        "target_name": rec.get("target_name"),
        "description": rec.get("description"),
        "tags": rec.get("tags") or [],
        "origin": rec.get("origin"),
        "source_session": rec.get("source_session"),
        "agent_slot": rec.get("agent_slot"),
        "reason": rec.get("reason"),
        "duplicate_of": rec.get("duplicate_of"),
        "created_at": rec.get("created_at"),
        "expires_at": rec.get("expires_at"),
        "content": rec.get("content") or "",
    }


@router.get("/pending")
async def list_pending_skills(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _, config = load_existing_profile(manager, profile_id)
    store = _proposal_store(config)
    store.expire_stale()
    rows = store.list_pending()
    return {
        "pending": [_proposal_public(r) for r in rows],
        "count": len(rows),
    }


@router.get("/pending/{proposal_id}")
async def get_pending_skill(
    profile_id: str,
    proposal_id: str,
    manager: FromDishka[ProfileManager],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _, config = load_existing_profile(manager, profile_id)
    rec = _proposal_store(config).get(proposal_id)
    if not rec or rec.get("status") != "pending":
        raise HTTPException(status_code=404, detail="Proposal not found")
    return _proposal_public(rec)


@router.post("/pending/{proposal_id}/approve")
async def approve_pending_skill(
    profile_id: str,
    proposal_id: str,
    manager: FromDishka[ProfileManager],
    body: SkillPendingApproveRequest | None = None,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _, config = load_existing_profile(manager, profile_id)
    store = _proposal_store(config)
    mgr = _skills_manager(config)
    try:
        rec = store.approve(
            proposal_id,
            manager=mgr,
            assign_to=list((body.assign if body else []) or []),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Proposal not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "proposal": _proposal_public(rec), "reload_required": True}


@router.post("/pending/{proposal_id}/reject")
async def reject_pending_skill(
    profile_id: str,
    proposal_id: str,
    manager: FromDishka[ProfileManager],
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _, config = load_existing_profile(manager, profile_id)
    try:
        rec = _proposal_store(config).reject(proposal_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Proposal not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "proposal": _proposal_public(rec)}


@router.post("/pending/{proposal_id}/merge")
async def merge_pending_skill(
    profile_id: str,
    proposal_id: str,
    manager: FromDishka[ProfileManager],
    body: SkillPendingMergeRequest,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _, config = load_existing_profile(manager, profile_id)
    mgr = _skills_manager(config)
    try:
        rec = _proposal_store(config).merge(proposal_id, body.target, manager=mgr)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "proposal": _proposal_public(rec), "reload_required": True}


@router.get("/{skill_name}")
async def show_skill(
    profile_id: str,
    manager: FromDishka[ProfileManager],
    skill_name: str,
    key_info: dict = Depends(verify_api_key),
    x_holix_profile: str | None = Header(None),
    x_holix_profile_key: str | None = Header(None, alias="X-Holix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_holix_profile, x_holix_profile_key)
    _, config = load_existing_profile(manager, profile_id)
    skills_dir = Path(config.skills_dir)
    skill = None
    try:
        flat = resolve_skill_markdown_path(skills_dir, skill_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid skill name") from exc
    if flat.exists():
        skill = parse_skill_file(flat, root=skills_dir)
    if not skill:
        for sf in discover_skill_files(skills_dir):
            parsed = parse_skill_file(sf, root=skills_dir)
            if parsed and parsed.get("name") == skill_name:
                skill = parsed
                break
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    assigns = agents_for_skill(getattr(config, "skill_assignments", {}) or {}, skill_name)
    return {
        "name": skill_name,
        "description": skill.get("description"),
        "tags": skill.get("tags") or [],
        "content": skill.get("content", ""),
        "assigned_agents": assigns,
        "yaml_agents": skill.get("agents") or skill.get("agent_roles"),
    }
