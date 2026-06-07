"""Persist user-invocable hub skills as slash commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.hub.normalize import discover_skill_files, parse_skill_file


def _lookup_skill(skills_dir: Path, name: str) -> dict[str, Any] | None:
    root = Path(skills_dir)
    flat = root / f"{name}.md"
    if flat.exists():
        return parse_skill_file(flat)
    for skill_file in discover_skill_files(root):
        parsed = parse_skill_file(skill_file)
        if parsed and parsed.get("name") == name:
            return parsed
    return None


def slash_registry_path(skills_dir: Path) -> Path:
    return Path(skills_dir).parent / "skill-slash.json"


def load_skill_slash_commands(
    skills_dir: Path,
    *,
    agent_slot: str = "main",
    skill_assignments: dict | None = None,
) -> list[tuple[str, str]]:
    """Slash commands from registry file, filtered for agent slot."""
    path = slash_registry_path(skills_dir)
    if not path.exists():
        return _slash_from_skills_dir(skills_dir, agent_slot=agent_slot, skill_assignments=skill_assignments)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    from core.skills.assignments import is_skill_allowed_for_agent

    out: list[tuple[str, str]] = []
    for item in data.get("commands", []):
        cmd = item.get("command")
        desc = item.get("description", "Hub skill")
        skill_name = item.get("skill_name") or (cmd or "").lstrip("/")
        if not cmd or not skill_name:
            continue
        skill = _lookup_skill(skills_dir, skill_name) or {"name": skill_name}
        if not is_skill_allowed_for_agent(skill, agent_slot, skill_assignments):
            continue
        out.append((cmd, desc))
    return out


def _slash_from_skills_dir(
    skills_dir: Path,
    *,
    agent_slot: str = "main",
    skill_assignments: dict | None = None,
) -> list[tuple[str, str]]:
    from core.skills.assignments import is_skill_allowed_for_agent

    commands: list[tuple[str, str]] = []
    root = Path(skills_dir)
    for skill_file in discover_skill_files(root):
        skill = parse_skill_file(skill_file)
        if not skill:
            continue
        invocable = skill.get("user-invocable", skill.get("user_invocable", True))
        if invocable is False:
            continue
        name = skill.get("name")
        if not name or not is_skill_allowed_for_agent(skill, agent_slot, skill_assignments):
            continue
        commands.append((f"/{name}", skill.get("description", "Skill")[:80]))
    return commands


def rebuild_slash_registry(skills_dir: Path) -> None:
    """Scan skills + hub bundles for user-invocable skills."""
    commands: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(name: str, description: str) -> None:
        cmd = f"/{name}"
        if cmd in seen:
            return
        seen.add(cmd)
        commands.append({"command": cmd, "skill_name": name, "description": description[:80]})

    root = Path(skills_dir)
    for skill_file in discover_skill_files(root):
        skill = parse_skill_file(skill_file)
        if not skill:
            continue
        invocable = skill.get("user-invocable", skill.get("user_invocable", True))
        if invocable is False:
            continue
        name = skill.get("name")
        if name:
            _add(name, skill.get("description", "Skill"))

    path = slash_registry_path(skills_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "commands": commands}, indent=2), encoding="utf-8")