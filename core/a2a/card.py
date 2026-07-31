"""Build A2A Agent Card for a Holix profile."""

from __future__ import annotations

from typing import Any

from core.a2a.config import A2AConfig, load_a2a_config


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

    # Optional: surface installed skills as A2A skills (bounded)
    try:
        from core.di import resolve_runtime_config
        from core.profile import ProfileManager
        from core.skills.manager import SkillsManager

        prof = ProfileManager().load_profile(profile)
        runtime = resolve_runtime_config(prof)
        mgr = SkillsManager(runtime)
        listed = []
        try:
            listed = list(mgr.list_skills() or [])[:12]
        except Exception:
            listed = []
        for item in listed:
            if isinstance(item, dict):
                sid = str(item.get("name") or item.get("id") or "").strip()
                desc = str(item.get("description") or "")[:240]
            else:
                sid = str(getattr(item, "name", "") or "").strip()
                desc = str(getattr(item, "description", "") or "")[:240]
            if not sid:
                continue
            skills.append(
                {
                    "id": f"skill-{sid}"[:64],
                    "name": sid,
                    "description": desc or f"Holix skill: {sid}",
                    "tags": ["skill"],
                    "inputModes": ["text/plain"],
                    "outputModes": ["text/plain"],
                }
            )
    except Exception:
        pass

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
    }
