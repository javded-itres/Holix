"""Install or remove optional decision and similarity skills.

The main agent sees every skill file in the profile. These skills stay out of
the profile until a command copies them in.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

DECISION_SKILL = "typed-decision"
EMBEDDINGS_SKILL = "text-similarity"


class SkillSwitchError(ValueError):
    pass


def skill_file(skills_dir: Path, name: str) -> Path:
    return Path(skills_dir) / f"{name}.md"


def skill_installed(skills_dir: Path, name: str) -> bool:
    return skill_file(skills_dir, name).is_file()


def set_opt_in_skill(skills_dir: Path, name: str, enabled: bool) -> None:
    from core.skills.bundled import load_opt_in_skill, remove_opt_in_skill

    if enabled:
        parsed = load_opt_in_skill(name)
        if parsed is None:
            raise SkillSwitchError(f"Unknown optional skill: {name}")
        from core.hub.normalize import write_flat_skill

        dest = skill_file(skills_dir, name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        write_flat_skill(dest, parsed)
    else:
        remove_opt_in_skill(Path(skills_dir), name)
    try:
        from core.hub.slash_registry import rebuild_slash_registry

        rebuild_slash_registry(Path(skills_dir))
    except Exception:
        pass


def apply_skill_switch(
    block: dict[str, Any] | None,
    *,
    block_enabled: bool,
    skills_dir: Path,
    name: str,
    enabled: bool,
) -> dict[str, Any]:
    if enabled and not block_enabled:
        raise SkillSwitchError("Turn the model on before enabling this skill.")
    out = dict(block or {})
    skills = dict(out.get("skills") or {})
    skills[name] = bool(enabled)
    out["skills"] = skills
    set_opt_in_skill(skills_dir, name, enabled)
    return out


def clear_skill(block: dict[str, Any] | None, skills_dir: Path, name: str) -> dict[str, Any]:
    out = dict(block or {})
    skills = dict(out.get("skills") or {})
    skills[name] = False
    out["skills"] = skills
    set_opt_in_skill(skills_dir, name, False)
    return out
