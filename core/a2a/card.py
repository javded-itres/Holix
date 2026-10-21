"""Build A2A Agent Card for a Holix profile."""

from __future__ import annotations

import logging
from typing import Any

from core.a2a.config import A2AConfig, load_a2a_config

logger = logging.getLogger(__name__)

# Enough for a caller to choose this agent. The full skill text stays local.
_SKILL_LIMIT = 12


def a2a_skill_from_holix(skill: dict[str, Any]) -> dict[str, Any] | None:
    """One installed Holix skill as an A2A AgentSkill. None when it has no name."""
    sid = str(skill.get("name") or skill.get("id") or "").strip()
    if not sid:
        return None
    desc = str(skill.get("description") or "").strip()
    return {
        "id": f"skill-{sid}"[:64],
        "name": sid,
        "description": (desc or f"Holix skill: {sid}")[:240],
        "tags": ["skill"],
        "inputModes": ["text/plain"],
        "outputModes": ["text/plain"],
    }


def _installed_a2a_skills(profile: str) -> list[dict[str, Any]]:
    """Skills assigned to the main agent. Empty when the profile cannot be read."""
    try:
        from core.di import resolve_runtime_config
        from core.profile import ProfileManager
        from core.skills.manager import SkillsManager

        runtime = resolve_runtime_config(ProfileManager().load_profile(profile))
        manager = SkillsManager(runtime)
        # Card reads are frequent. Do not embed every skill into the vector store.
        manager.load_all_skills(defer_index=True)
        chosen = manager.filter_skills_for_agent(list(manager.all_skills.values()), "main")
        chosen.sort(key=lambda item: str(item.get("name") or ""))
        entries: list[dict[str, Any]] = []
        for item in chosen:
            if not isinstance(item, dict):
                continue
            entry = a2a_skill_from_holix(item)
            if entry is None:
                continue
            entries.append(entry)
            if len(entries) >= _SKILL_LIMIT:
                break
        return entries
    except Exception:
        logger.debug("A2A card skipped installed skills for %s", profile, exc_info=True)
        return []


def _auth_declaration() -> dict[str, Any]:
    """Tell a caller that a bearer is required. The key itself stays off the card."""
    try:
        from config import settings

        if not settings.effective_require_auth:
            return {}
    except Exception:
        return {}
    return {
        "securitySchemes": {
            "bearer": {
                "type": "http",
                "scheme": "bearer",
                "description": "Holix gateway API key, issued out of band.",
            }
        },
        "security": [{"bearer": []}],
    }


def build_agent_card(
    profile: str = "default",
    *,
    public_url: str | None = None,
    config: A2AConfig | None = None,
) -> dict[str, Any]:
    """Return Agent Card JSON (discovery document)."""
    cfg = config or load_a2a_config(profile)
    url = (public_url or cfg.public_url or "").strip().rstrip("/")
    if not url:
        # Relative service base; clients should resolve against gateway origin
        url = "/a2a"

    name = cfg.card_name or f"Holix ({profile})"
    description = cfg.card_description or (
        "Holix self-improving AI agent with memory, skills, MCP tools, "
        "sub-agents, and SDD. Exposed via the Agent2Agent (A2A) protocol."
    )

    skills: list[dict[str, Any]] = [
        {
            "id": "general-assistant",
            "name": "General assistant",
            "description": "Answer questions, write code, run tools in the Holix workspace.",
            "tags": ["general", "coding", "tools"],
            "examples": [
                "Explain this stack and suggest next steps",
                "Implement a feature and open a PR plan",
            ],
            "inputModes": ["text/plain"],
            "outputModes": ["text/plain"],
        }
    ]

    skills.extend(_installed_a2a_skills(profile))

    return {
        "name": name,
        "description": description,
        "url": url,
        "version": cfg.card_version,
        "protocolVersion": "0.3.0",
        "preferredTransport": "JSONRPC",
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
            "stateTransitionHistory": False,
        },
        "defaultInputModes": ["text/plain", "text"],
        "defaultOutputModes": ["text/plain", "text"],
        "skills": skills,
        "supportsAuthenticatedExtendedCard": False,
        "provider": {
            "organization": "Holix",
            "url": "https://holix-agent.ru",
        },
        "additionalInterfaces": [
            {
                "url": url,
                "transport": "JSONRPC",
            }
        ],
        # Holix extensions (non-normative metadata)
        "metadata": {
            "holix_profile": profile,
            "framework": "Holix",
        },
        **_auth_declaration(),
    }
