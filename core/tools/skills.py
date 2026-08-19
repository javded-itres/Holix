"""Agent tools for progressive skill loading and staged skill writes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.hub.normalize import slugify_skill_name
from core.skills.proposal import SkillProposalStore, is_protected_skill
from core.tools.base import BaseTool
from core.tools.execution_context import get_conversation_id, get_profile_name


def _skills_manager():
    from core.di import resolve_runtime_config
    from core.profile import ProfileManager
    from core.skills.manager import SkillsManager

    profile = (get_profile_name() or "").strip() or "default"
    manager = ProfileManager()
    if manager.profile_exists(profile):
        cfg = manager.load_profile(profile)
        mgr = SkillsManager(resolve_runtime_config(cfg))
    else:
        mgr = SkillsManager(resolve_runtime_config())
    if not mgr.all_skills:
        mgr.load_all_skills(defer_index=True)
    return mgr


def _read_support_file(skill: dict[str, Any], rel: str) -> str:
    raw = (rel or "").strip().lstrip("/")
    if not raw or ".." in Path(raw).parts:
        raise ValueError("invalid support file path")
    allowed_roots = ("references", "templates", "scripts", "examples", "assets")
    first = Path(raw).parts[0]
    if first not in allowed_roots:
        raise ValueError(f"path must be under {', '.join(allowed_roots)} (got {raw!r})")
    base = Path(str(skill.get("filepath") or ""))
    if base.name == "SKILL.md":
        root = base.parent
    else:
        root = base.parent / str(skill.get("name") or "")
        if not root.is_dir():
            raise FileNotFoundError(raw)
    target = (root / raw).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        raise ValueError("path escapes the skill directory")
    if not target.is_file():
        raise FileNotFoundError(raw)
    return target.read_text(encoding="utf-8", errors="replace")


class SkillViewTool(BaseTool):
    """List skill index or load one skill (and optional support file)."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "skill_view"
        self.description = (
            "Load a Holix skill. Omit name to list the skill index "
            "(name + description). Pass name for the full SKILL.md. "
            "Optional path loads a support file under references/ templates/ "
            "scripts/ examples/ assets/."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Skill name. Empty = list index.",
                },
                "path": {
                    "type": "string",
                    "description": "Optional support file relative to the skill dir",
                },
            },
        }

    async def execute(self, name: str = "", path: str = "", **_: Any) -> str:
        mgr = _skills_manager()
        want = slugify_skill_name(name) if name else ""
        if not want:
            rows = []
            for skill_name, skill in sorted(mgr.all_skills.items()):
                desc = (skill.get("description") or "").strip()
                origin = skill.get("origin") or skill.get("_source") or ""
                rows.append(f"- {skill_name}: {desc}" + (f" [{origin}]" if origin else ""))
            if not rows:
                return "No skills installed."
            return "Skill index:\n" + "\n".join(rows)

        skill = mgr.all_skills.get(want)
        if not skill:
            return f"Skill {want!r} not found. Call skill_view() without name for the index."
        if path:
            try:
                return _read_support_file(skill, path)
            except (OSError, ValueError) as exc:
                return f"Could not read {path}: {exc}"
        mgr.mark_skill_used(want, conversation_id=get_conversation_id())
        desc = skill.get("description") or ""
        tags = ", ".join(skill.get("tags") or [])
        body = (skill.get("content") or "").strip()
        header = [f"# {want}", f"Description: {desc}"]
        if tags:
            header.append(f"Tags: {tags}")
        return "\n".join(header) + "\n\n" + body


class SkillManageTool(BaseTool):
    """Create or patch a skill by staging a pending proposal."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "skill_manage"
        self.description = (
            "Create or patch a reusable skill. Writes are staged under "
            "_pending for human approval — they do NOT become live skills "
            "and are not assigned to main. Prefer patch over create when a "
            "similar skill exists. Use skill_view first."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "patch"],
                    "description": "create a new draft or patch an existing skill",
                },
                "name": {
                    "type": "string",
                    "description": "Skill slug (existing name for patch)",
                },
                "content": {
                    "type": "string",
                    "description": "Full SKILL.md body (When to Use / Procedure / Pitfalls / Verification)",
                },
                "description": {
                    "type": "string",
                    "description": "One-line description (≤ 80 chars)",
                },
                "tags": {
                    "type": "string",
                    "description": "Comma-separated tags",
                },
                "old_string": {
                    "type": "string",
                    "description": "For patch: exact text to replace (preferred over full rewrite)",
                },
                "new_string": {
                    "type": "string",
                    "description": "For patch: replacement text",
                },
            },
            "required": ["action", "name"],
        }

    async def execute(
        self,
        action: str = "create",
        name: str = "",
        content: str = "",
        description: str = "",
        tags: str = "",
        old_string: str = "",
        new_string: str = "",
        **_: Any,
    ) -> str:
        action = (action or "create").strip().lower()
        if action not in {"create", "patch"}:
            return "action must be create or patch (delete is not available via this tool)."
        slug = slugify_skill_name(name)
        if not slug:
            return "name is required."
        mgr = _skills_manager()
        tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
        existing = mgr.all_skills.get(slug)
        if is_protected_skill(existing, slug):
            return f"Refused: {slug!r} is a bundled/hub skill and cannot be overwritten."

        body = (content or "").strip()
        if action == "patch":
            if not existing:
                return f"No live skill named {slug!r} to patch. Use action=create or skill_view()."
            current = (existing.get("content") or "").strip()
            if old_string:
                if old_string not in current:
                    return "old_string not found in the current skill. Call skill_view first."
                body = current.replace(old_string, new_string or "", 1)
            elif not body:
                return "patch needs content or old_string/new_string."
            description = description or str(existing.get("description") or "")
            if not tag_list:
                tag_list = list(existing.get("tags") or [])

        if not body:
            return "content is required (When to Use / Procedure / Pitfalls / Verification)."

        store = SkillProposalStore(mgr.skills_dir)
        try:
            from core.skills.lifecycle import resolve_skill_locale, settle_proposal
            from core.skills.quality import heuristic_quality

            profile = get_profile_name() or "default"
            locale = resolve_skill_locale(profile)
            rec = store.stage(
                name=slug,
                action=action,
                content=body,
                description=description or slug,
                tags=tag_list,
                target_name=slug,
                origin="skill_manage",
                source_session=get_conversation_id(),
                reason="skill_manage",
                quality_score=heuristic_quality(
                    {
                        "action": action,
                        "description": description,
                        "content": body,
                    }
                ),
                locale=locale,
            )
            rec = settle_proposal(store, rec, manager=mgr, profile=profile, skill_data=rec)
        except ValueError as exc:
            return f"Could not stage skill: {exc}"
        score = rec.get("quality_score") or 0
        if rec.get("auto_applied"):
            return (
                f"Auto-approved {action} '{rec.get('name')}' (score {score}). Live skill written."
            )
        return (
            f"Staged {action} for '{rec.get('name')}' as {rec.get('id')} "
            f"(score {score}). Approve in Settings → Skills or tap the messenger buttons."
        )
