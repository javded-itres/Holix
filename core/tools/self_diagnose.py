"""Tool: inspect this session and optionally stage a skill fix."""

from __future__ import annotations

from typing import Any

from core.runtime.self_diagnose import SELF_DIAGNOSE_TOOL
from core.tools.base import BaseTool
from core.tools.execution_context import get_conversation_id, get_profile_name
from core.tools.result import tool_err, tool_ok


class SelfDiagnoseTool(BaseTool):
    """Run session self-diagnosis for «проверь себя» / you are doing it wrong."""

    def __init__(self) -> None:
        super().__init__()
        self.name = SELF_DIAGNOSE_TOOL
        self.description = (
            "Inspect this conversation: user asks vs tools vs assistant claims, "
            "LLM turn stats from trajectory, and skills that may have caused the "
            "mistake. Call this FIRST when the user says «проверь себя», "
            "«почему ты делаешь не так», «ты отвечаешь неправильно», "
            "check yourself, or similar. Then answer from the report. "
            "Can stage a skill patch (still goes through skill approval)."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "complaint": {
                    "type": "string",
                    "description": "User's complaint (optional; last user message is used if empty)",
                },
                "fix_skills": {
                    "type": "boolean",
                    "default": True,
                    "description": "Stage a patch when a live skill taught the wrong procedure",
                },
            },
        }

    async def execute(self, complaint: str = "", fix_skills: bool = True, **_: Any) -> str:
        from core.runtime.self_diagnose import diagnose_session

        cid = get_conversation_id() or "default"
        profile = get_profile_name() or "default"
        want = (complaint or "").strip()
        messages: list[dict[str, Any]] = []
        trajectory: list[dict[str, Any]] = []
        skills: list[dict[str, Any]] = []

        try:
            from core.tools.session_memory import _resolve_memory

            memory = _resolve_memory()
            messages = await memory.get_conversation(cid, limit=80)
        except Exception:
            messages = []

        if not want:
            for msg in reversed(messages):
                if str(msg.get("role") or "") == "user":
                    raw = msg.get("content")
                    want = raw if isinstance(raw, str) else str(raw or "")
                    break

        try:
            from core.runtime.trajectory import TrajectoryLog

            trajectory = TrajectoryLog(profile).tail(cid, limit=200)
        except Exception:
            trajectory = []

        mgr = None
        try:
            from core.tools.skills import _skills_manager

            mgr = _skills_manager()
            for name, skill in (mgr.all_skills or {}).items():
                skills.append(
                    {
                        "name": name,
                        "description": str(skill.get("description") or ""),
                        "content": str(skill.get("content") or ""),
                        "protected": False,
                        "filepath": str(skill.get("filepath") or ""),
                    }
                )
        except Exception:
            mgr = None

        if mgr is not None:
            try:
                from core.skills.proposal import is_protected_skill

                for item in skills:
                    live = (mgr.all_skills or {}).get(item["name"])
                    item["protected"] = is_protected_skill(live, item["name"])
            except Exception:
                pass

        report = diagnose_session(
            complaint=want,
            messages=messages,
            trajectory=trajectory,
            skills=skills,
        )
        report["conversation_id"] = cid
        report["profile"] = profile

        staged: list[dict[str, Any]] = []
        if fix_skills and mgr is not None:
            try:
                from core.tools.plan_mode_state import is_plan_mode

                if is_plan_mode():
                    report["skill_fixes"] = {
                        "skipped": "plan_mode",
                        "detail": "Exit plan_mode before patching skills.",
                    }
                else:
                    staged = await _stage_delivery_fixes(mgr, skills)
                    report["skill_fixes"] = staged
            except Exception as exc:
                report["skill_fixes"] = [{"error": str(exc)}]
        elif not fix_skills:
            report["skill_fixes"] = []

        if not messages and not trajectory:
            return tool_err(
                "no_session_data",
                "No conversation or trajectory for this session yet.",
                **{k: v for k, v in report.items() if k != "ok"},
            )
        return tool_ok(**{k: v for k, v in report.items() if k != "ok"})


async def _stage_delivery_fixes(mgr: Any, skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from core.runtime.self_diagnose import rewrite_delivery_skill
    from core.skills.lifecycle import resolve_skill_locale, settle_proposal
    from core.skills.proposal import SkillProposalStore, is_protected_skill
    from core.skills.quality import heuristic_quality
    from core.tools.execution_context import get_conversation_id, get_profile_name

    out: list[dict[str, Any]] = []
    profile = get_profile_name() or "default"
    store = SkillProposalStore(mgr.skills_dir)
    for item in skills:
        name = str(item.get("name") or "")
        live = (mgr.all_skills or {}).get(name)
        if is_protected_skill(live, name):
            continue
        current = str(item.get("content") or "")
        patched = rewrite_delivery_skill(current)
        if not patched or patched == current:
            continue
        rec = store.stage(
            name=name,
            action="patch",
            content=patched,
            description=str(item.get("description") or name),
            tags=list((live or {}).get("tags") or []),
            target_name=name,
            origin="self_diagnose",
            source_session=get_conversation_id(),
            reason="self_diagnose: chat delivery must use send_chat_files",
            quality_score=heuristic_quality(
                {
                    "action": "patch",
                    "description": item.get("description") or name,
                    "content": patched,
                }
            ),
            locale=resolve_skill_locale(profile),
        )
        rec = settle_proposal(store, rec, manager=mgr, profile=profile, skill_data=rec)
        out.append(
            {
                "name": name,
                "proposal_id": rec.get("id"),
                "auto_applied": bool(rec.get("auto_applied")),
                "quality_score": rec.get("quality_score"),
                "status": "live" if rec.get("auto_applied") else "staged",
            }
        )
    return out
