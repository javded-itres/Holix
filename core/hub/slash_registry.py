"""Persist user-invocable hub skills as slash commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.hub.normalize import discover_skill_files, parse_skill_file

# One parse of the skills tree, reused until a file's size or mtime changes.
# Keyed by the skills directory. Each value is (signature, flat stem -> skill,
# frontmatter name -> first skill in discover order).
_SKILL_INDEX: dict[
    str,
    tuple[
        tuple[tuple[str, int, int], ...],
        dict[str, dict[str, Any] | None],
        dict[str, dict[str, Any]],
    ],
] = {}


def _file_signature(path: Path) -> tuple[str, int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (str(path), int(stat.st_mtime_ns), int(stat.st_size))


def _skill_index(
    root: Path,
) -> tuple[dict[str, dict[str, Any] | None], dict[str, dict[str, Any]]]:
    """Parse each skill file once. Flat ``<name>.md`` stays a separate map."""
    files = discover_skill_files(root)
    signature: list[tuple[str, int, int]] = []
    for path in files:
        item = _file_signature(path)
        if item is not None:
            signature.append(item)
    key = str(root)
    cached = _SKILL_INDEX.get(key)
    frozen = tuple(signature)
    if cached is not None and cached[0] == frozen:
        return cached[1], cached[2]

    flat: dict[str, dict[str, Any] | None] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for path in files:
        parsed = parse_skill_file(path)
        if path.parent == root and path.name.lower() != "skill.md":
            flat[path.stem] = parsed
        name = parsed.get("name") if parsed else None
        if name and name not in by_name and parsed is not None:
            by_name[name] = parsed
    if len(_SKILL_INDEX) > 8:
        _SKILL_INDEX.pop(next(iter(_SKILL_INDEX)))
    _SKILL_INDEX[key] = (frozen, flat, by_name)
    return flat, by_name


def slash_registry_path(skills_dir: Path) -> Path:
    from core.profile.names import assert_under_profiles_root

    root = assert_under_profiles_root(Path(skills_dir))
    return root.parent / "skill-slash.json"


def skill_invoke_autocomplete_commands(
    skills_dir: Path,
    *,
    agent_slot: str = "main",
    skill_assignments: dict | None = None,
) -> list[tuple[str, str]]:
    """Autocomplete entries as `/skill <name>` (not bare `/<name>`)."""
    return [
        (f"/skill {cmd.lstrip('/')}", desc)
        for cmd, desc in load_skill_slash_commands(
            skills_dir,
            agent_slot=agent_slot,
            skill_assignments=skill_assignments,
        )
    ]


def load_skill_slash_commands(
    skills_dir: Path,
    *,
    agent_slot: str = "main",
    skill_assignments: dict | None = None,
) -> list[tuple[str, str]]:
    """Slash commands from registry file, filtered for agent slot."""
    path = slash_registry_path(skills_dir)
    if not path.exists():
        return _slash_from_skills_dir(
            skills_dir, agent_slot=agent_slot, skill_assignments=skill_assignments
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    from core.skills.assignments import is_skill_allowed_for_agent

    root = Path(skills_dir)
    flat, by_name = _skill_index(root)
    out: list[tuple[str, str]] = []
    for item in data.get("commands", []):
        cmd = item.get("command")
        desc = item.get("description", "Hub skill")
        skill_name = item.get("skill_name") or (cmd or "").lstrip("/")
        if not cmd or not skill_name:
            continue
        skill = _skill_from_index(skill_name, flat, by_name) or {"name": skill_name}
        if not is_skill_allowed_for_agent(skill, agent_slot, skill_assignments):
            continue
        out.append((cmd, desc))
    return out


def _skill_from_index(
    name: str,
    flat: dict[str, dict[str, Any] | None],
    by_name: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Flat ``<name>.md`` wins, including a file that does not parse."""
    if name in flat:
        return flat[name]
    return by_name.get(name)


def _slash_from_skills_dir(
    skills_dir: Path,
    *,
    agent_slot: str = "main",
    skill_assignments: dict | None = None,
) -> list[tuple[str, str]]:
    from core.skills.assignments import is_skill_allowed_for_agent

    commands: list[tuple[str, str]] = []
    _, by_name = _skill_index(Path(skills_dir))
    for skill in by_name.values():
        invocable = skill.get("user-invocable", skill.get("user_invocable", True))
        if invocable is False:
            continue
        name = skill.get("name")
        if not name or not is_skill_allowed_for_agent(skill, agent_slot, skill_assignments):
            continue
        commands.append((f"/{name}", str(skill.get("description") or "Skill")[:80]))
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

    from core.profile.names import assert_under_profiles_root

    path = slash_registry_path(skills_dir)
    assert_under_profiles_root(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "commands": commands}, indent=2), encoding="utf-8")
