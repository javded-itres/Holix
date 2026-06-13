"""Tools for agent soul, user profile, and first-run initialization."""

from __future__ import annotations

from core.profile.init import complete_init, init_pending
from core.profile.soul import is_soul_empty_or_placeholder, update_soul_content
from core.profile.user_profile import (
    record_onboarding_episode,
    sync_user_to_strategic_memory,
    update_user_profile,
)
from core.tools.base import BaseTool
from core.tools.execution_context import get_memory_facade


def _resolve_profile_name() -> str:
    facade = get_memory_facade()
    if facade is not None:
        name = getattr(getattr(facade, "config", None), "profile_name", None)
        if name:
            return str(name).strip() or "default"
    from core.env_loader import active_profile_name

    return active_profile_name() or "default"


class SaveAgentSoulTool(BaseTool):
    """Persist agent personality into profile SOUL.md."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "save_agent_soul"
        self.description = (
            "Save the agent's personality / soul / identity into the profile SOUL.md file. "
            "If SOUL is empty or still a placeholder, writes the full document; otherwise appends. "
            "Use when the user describes personality or asks to save soul/личность/душу/identity."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Personality traits, values, tone, and identity to persist",
                },
                "section": {
                    "type": "string",
                    "description": "Optional markdown section title when appending",
                },
            },
            "required": ["content"],
        }

    async def execute(self, content: str, section: str | None = None) -> str:
        profile = _resolve_profile_name()
        try:
            action = update_soul_content(profile, content, section=section)
        except ValueError as exc:
            return f"Error: {exc}"
        return f"Agent soul {action} in profiles/{profile}/SOUL.md"


class SaveUserProfileTool(BaseTool):
    """Persist facts about the human user."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "save_user_profile"
        self.description = (
            "Save information about the human user to USER.md and long-term memory "
            "(name, how to address them, work style, language, notes). "
            "Call during onboarding and whenever the user shares stable preferences."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "User's name"},
                "preferred_name": {
                    "type": "string",
                    "description": "How the user wants to be addressed",
                },
                "work_style": {
                    "type": "string",
                    "description": "How they prefer to collaborate (pace, detail, tools)",
                },
                "language_preference": {
                    "type": "string",
                    "description": "Preferred language for communication",
                },
                "notes": {
                    "type": "string",
                    "description": "Other stable facts about the user",
                },
                "append_notes": {
                    "type": "boolean",
                    "description": "Append to existing notes instead of replacing",
                    "default": True,
                },
            },
        }

    async def execute(
        self,
        name: str | None = None,
        preferred_name: str | None = None,
        work_style: str | None = None,
        language_preference: str | None = None,
        notes: str | None = None,
        append_notes: bool = True,
    ) -> str:
        profile = _resolve_profile_name()
        if not any((name, preferred_name, work_style, language_preference, notes)):
            return "Error: provide at least one user field to save"

        action, fields = update_user_profile(
            profile,
            name=name,
            preferred_name=preferred_name,
            work_style=work_style,
            language_preference=language_preference,
            notes=notes,
            append_notes=append_notes,
        )
        await sync_user_to_strategic_memory(profile, fields)
        saved = ", ".join(k for k, v in fields.items() if v)
        return f"User profile {action} (profiles/{profile}/USER.md). Saved: {saved}"


class CompleteAgentInitializationTool(BaseTool):
    """Finish first-run onboarding and remove INIT.md."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "complete_agent_initialization"
        self.description = (
            "Mark first-time onboarding complete: requires user name in USER.md and a customized "
            "SOUL.md. Deletes INIT.md so normal operation begins. Call only after introduction "
            "and collecting user + agent personality."
        )
        self.risk_level = "low"
        self.parameters = {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Short summary of what was learned during onboarding",
                },
                "force": {
                    "type": "boolean",
                    "description": "Complete even if some fields are missing (not recommended)",
                    "default": False,
                },
            },
        }

    async def execute(self, summary: str | None = None, force: bool = False) -> str:
        profile = _resolve_profile_name()
        if not init_pending(profile):
            return "Initialization already completed (INIT.md not present)."

        from core.profile.user_profile import _parse_user_fields, _read_user_raw

        fields = _parse_user_fields(_read_user_raw(profile))
        missing: list[str] = []
        if not fields.get("name"):
            missing.append("user name (save_user_profile)")
        if is_soul_empty_or_placeholder(profile):
            missing.append("agent soul (save_agent_soul)")

        if missing and not force:
            return (
                "Cannot complete initialization yet. Missing: "
                + ", ".join(missing)
                + ". Collect them, then call again or use force=true."
            )

        if not complete_init(profile):
            return "Error: could not remove INIT.md"

        episode = summary or "Onboarding completed."
        await record_onboarding_episode(profile, episode)
        await sync_user_to_strategic_memory(profile, fields, source="onboarding_complete")

        return (
            f"Initialization complete for profile '{profile}'. INIT.md removed. "
            "SOUL.md and USER.md are active."
        )


def register_profile_identity_tools(registry) -> None:
    registry.register(SaveAgentSoulTool())
    registry.register(SaveUserProfileTool())
    registry.register(CompleteAgentInitializationTool())