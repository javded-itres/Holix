"""Per-agent skill allowlists (profile assignments + skill frontmatter)."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set


def _normalize_agent_list(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Iterable):
        return None
    out = [str(x).strip() for x in value if str(x).strip()]
    return out or None


def skill_frontmatter_agents(skill: Dict[str, Any]) -> Optional[List[str]]:
    """Agents allowed by skill YAML (`agents` or `agent_roles`). None = any agent."""
    raw = skill.get("agents")
    if raw is None:
        raw = skill.get("agent_roles")
    return _normalize_agent_list(raw)


def whitelist_for_slot(
    assignments: Optional[Dict[str, List[str]]],
    slot: str,
) -> Optional[Set[str]]:
    """Profile whitelist for a slot. None = no profile restriction (all skill names)."""
    if not assignments:
        return None
    if slot in assignments:
        return set(assignments[slot] or [])
    if "main" in assignments:
        return set(assignments["main"] or [])
    return None


def is_skill_allowed_for_agent(
    skill: Dict[str, Any],
    agent_slot: str,
    assignments: Optional[Dict[str, List[str]]] = None,
) -> bool:
    """True if skill may be used by this agent/subagent slot."""
    name = skill.get("name")
    if not name:
        return False

    fm_agents = skill_frontmatter_agents(skill)
    if fm_agents is not None and agent_slot not in fm_agents:
        return False

    # Main agent: all profile skills (YAML `agents` is the only restriction).
    # skill_assignments limits sub-agents / specialists, not the primary agent.
    if agent_slot == "main":
        return True

    whitelist = whitelist_for_slot(assignments, agent_slot)
    if whitelist is not None:
        return name in whitelist

    return True


def known_agent_slots(
    assignments: Optional[Dict[str, List[str]]] = None,
    agent_models: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Roles used in `helix skills assign` (main + profile agents + predefined subagents)."""
    slots: Set[str] = {"main"}
    if agent_models:
        slots.update(agent_models.keys())
    if assignments:
        slots.update(assignments.keys())
    try:
        from core.subagents.registry import list_available_subagents

        slots.update(s["name"] for s in list_available_subagents())
    except Exception:
        pass
    return sorted(slots)


def assign_skill_to_agents(
    assignments: Dict[str, List[str]],
    skill_name: str,
    agent_slots: List[str],
) -> Dict[str, List[str]]:
    """Add skill_name to each agent slot's allowlist (creates entries as needed)."""
    out = {k: list(v) for k, v in assignments.items()}
    for slot in agent_slots:
        lst = list(out.get(slot, []))
        if skill_name not in lst:
            lst.append(skill_name)
        out[slot] = lst
    return out


def unassign_skill_from_agents(
    assignments: Dict[str, List[str]],
    skill_name: str,
    agent_slots: Optional[List[str]] = None,
) -> Dict[str, List[str]]:
    """Remove skill from given slots, or from all slots if agent_slots is None."""
    out = {k: list(v) for k, v in assignments.items()}
    targets = agent_slots if agent_slots is not None else list(out.keys())
    for slot in targets:
        if slot in out:
            out[slot] = [x for x in out[slot] if x != skill_name]
            if not out[slot]:
                del out[slot]
    return out


def normalize_skill_agent_slot(slot_id: str) -> str:
    """Map model-picker slot id to skill_assignments role name."""
    if not slot_id or slot_id in ("main", "legacy"):
        return "main"
    if slot_id.startswith("prov:"):
        return "main"
    return slot_id


def agents_for_skill(
    assignments: Dict[str, List[str]],
    skill_name: str,
) -> List[str]:
    """Agent slots that explicitly list this skill in skill_assignments."""
    return sorted(slot for slot, names in assignments.items() if skill_name in names)


def assign_created_skill(
    assignments: Dict[str, List[str]],
    skill_name: str,
    agent_slot: str,
) -> Dict[str, List[str]]:
    """Attach a newly created skill to the agent slot that produced it."""
    slot = (agent_slot or "main").strip() or "main"
    return assign_skill_to_agents(assignments, skill_name, [slot])


def apply_skills_to_agent_slots(
    config: Any,
    profile: str,
    manager: Any,
    skill_names: list[str],
    agents_csv: str,
) -> list[str]:
    """Persist skill_assignments for installed skill names. Returns agent slots used."""
    agent_list = [a.strip() for a in agents_csv.split(",") if a.strip()]
    slots = known_agent_slots(
        getattr(config, "skill_assignments", None),
        getattr(config, "agent_models", None),
    )
    agent_list = [a for a in agent_list if a in slots]
    if not agent_list or not skill_names:
        return []
    assigns = dict(getattr(config, "skill_assignments", {}) or {})
    for name in skill_names:
        assigns = assign_skill_to_agents(assigns, name, agent_list)
    config.skill_assignments = assigns
    manager.save_profile(profile, config)
    return agent_list