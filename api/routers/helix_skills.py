"""Helix management: skills list, search, assignments."""

from __future__ import annotations

from pathlib import Path

from cli.core import ProfileManager
from core.hub.normalize import discover_skill_files, parse_skill_file
from core.skills.assignments import agents_for_skill
from fastapi import APIRouter, Depends, Header, HTTPException, Query

from api.deps import verify_api_key
from api.schemas.helix import SkillAssignmentsPatchRequest
from api.services.helix_deps import profile_access

router = APIRouter(prefix="/api/helix/profiles/{profile_id}/skills", tags=["helix-skills"])


def _require_profile(profile_id: str) -> tuple[ProfileManager, object]:
    manager = ProfileManager()
    if not manager.profile_exists(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    return manager, manager.load_profile(profile_id)


def _skills_manager(config):
    from core.di import resolve_runtime_config
    from core.skills.manager import SkillsManager

    mgr = SkillsManager(resolve_runtime_config(config))
    mgr.load_all_skills()
    return mgr


@router.get("")
async def list_skills(
    profile_id: str,
    limit: int = Query(50, ge=1, le=500),
    agent: str | None = Query(None),
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_helix_profile_key: str | None = Header(None, alias="X-Helix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_helix_profile, x_helix_profile_key)
    _, config = _require_profile(profile_id)
    mgr = _skills_manager(config)
    slot = agent or "main"
    assigns = getattr(config, "skill_assignments", None) or {}
    skills = []
    for name in sorted(mgr.all_skills.keys()):
        skill = mgr.all_skills[name]
        if agent and not mgr.is_allowed_for_agent(skill, slot):
            continue
        skills.append({
            "name": name,
            "description": (skill.get("description") or "")[:200],
            "tags": skill.get("tags") or [],
            "assigned_agents": agents_for_skill(assigns, name),
        })
        if len(skills) >= limit:
            break
    return {"skills": skills, "count": len(skills)}


@router.get("/search")
async def search_skills(
    profile_id: str,
    q: str = Query(..., min_length=1),
    agent: str | None = Query(None),
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_helix_profile_key: str | None = Header(None, alias="X-Helix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_helix_profile, x_helix_profile_key)
    _, config = _require_profile(profile_id)
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
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_helix_profile_key: str | None = Header(None, alias="X-Helix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_helix_profile, x_helix_profile_key)
    _, config = _require_profile(profile_id)
    return {"assignments": getattr(config, "skill_assignments", None) or {}}


@router.patch("/assignments")
async def patch_assignments(
    profile_id: str,
    body: SkillAssignmentsPatchRequest,
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_helix_profile_key: str | None = Header(None, alias="X-Helix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_helix_profile, x_helix_profile_key)
    manager, config = _require_profile(profile_id)
    config.skill_assignments = body.assignments
    manager.save_profile(profile_id, config)
    return {"assignments": config.skill_assignments, "reload_required": True}


@router.post("/seed-bundled")
async def seed_bundled(
    profile_id: str,
    force: bool = Query(False),
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_helix_profile_key: str | None = Header(None, alias="X-Helix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_helix_profile, x_helix_profile_key)
    manager, config = _require_profile(profile_id)
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


@router.get("/{skill_name}")
async def show_skill(
    profile_id: str,
    skill_name: str,
    key_info: dict = Depends(verify_api_key),
    x_helix_profile: str | None = Header(None),
    x_helix_profile_key: str | None = Header(None, alias="X-Helix-Profile-Key"),
):
    profile_access(profile_id, key_info, x_helix_profile, x_helix_profile_key)
    _, config = _require_profile(profile_id)
    skills_dir = Path(config.skills_dir)
    skill = None
    flat = skills_dir / f"{skill_name}.md"
    if flat.exists():
        skill = parse_skill_file(flat)
    if not skill:
        for sf in discover_skill_files(skills_dir):
            parsed = parse_skill_file(sf)
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