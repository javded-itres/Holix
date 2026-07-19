"""Agent tools to list / scaffold / enable / disable drop-in agent extensions."""

from __future__ import annotations

import json
from typing import Any

from core.tools.base import BaseTool

# Actions that author or re-enable extensions (local single-operator only).
_MUTATING_CREATE_ACTIONS = frozenset({"create", "enable", "quarantine_clear"})
# Actions that change load set and should hot-reload when allowed.
_RELOAD_AFTER_ACTIONS = frozenset({"create", "disable", "enable", "quarantine_clear", "reload"})


def _profile(agent: Any) -> str:
    return str(getattr(getattr(agent, "config", None), "profile_name", None) or "default")


def _self_ext_allowed(agent: Any) -> bool:
    from core.extensions.self_ext_policy import agent_allows_self_extensions

    return agent_allows_self_extensions(agent)


def _hot_reload(agent: Any) -> dict[str, Any] | None:
    """Reload extensions on the live agent; return result dict or error payload."""
    if agent is None:
        return None
    try:
        if hasattr(agent, "reload_agent_extensions"):
            return agent.reload_agent_extensions()
        from core.extensions.agent_registry import reload_agent_extensions

        return reload_agent_extensions(agent)
    except Exception as exc:
        return {"ok": False, "error": f"hot_reload failed: {type(exc).__name__}: {exc}"}


class ManageAgentExtensionsTool(BaseTool):
    """Create and control profile-local agent extensions without editing Holix core."""

    def __init__(self, agent: Any | None = None) -> None:
        super().__init__()
        self._agent = agent
        self.name = "manage_agent_extensions"
        self.description = (
            "Manage Holix *agent* drop-in extensions (profile folder, not core). "
            "Actions: list, create, disable, enable, quarantine_clear, show_control, "
            "registered, reload. "
            "create/enable only in **local** single-operator mode (CLI/TUI) — "
            "not on Telegram/MAX multi-user bots. "
            "After create, the agent hot-reloads tools into the current session. "
            "If an extension breaks the agent, use disable. "
            "Emergency: env HOLIX_AGENT_EXTENSIONS_OFF=1."
        )
        self.risk_level = "medium"
        self.parameters = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "list",
                        "create",
                        "disable",
                        "enable",
                        "quarantine_clear",
                        "show_control",
                        "registered",
                        "reload",
                    ],
                    "description": "What to do",
                },
                "name": {
                    "type": "string",
                    "description": "Extension id (a-z, digits, underscore), required for create/disable/enable",
                },
                "description": {
                    "type": "string",
                    "description": "Human description for create",
                },
                "reason": {
                    "type": "string",
                    "description": "Why disabling (optional)",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Overwrite existing scaffold on create",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str = "list",
        name: str = "",
        description: str = "",
        reason: str = "",
        overwrite: bool = False,
        **kwargs: Any,
    ) -> str:
        profile = _profile(self._agent)
        action = (action or "list").strip().lower()
        try:
            if action in _MUTATING_CREATE_ACTIONS and not _self_ext_allowed(self._agent):
                from core.extensions.self_ext_policy import self_extension_denied_message

                return json.dumps(
                    {
                        "ok": False,
                        "error": "self_extensions_denied",
                        "action": action,
                        "message": self_extension_denied_message(),
                    },
                    ensure_ascii=False,
                    indent=2,
                )

            if action == "list":
                from core.extensions.control import list_local_agent_extension_folders

                rows = list_local_agent_extension_folders(profile)
                return json.dumps(
                    {"profile": profile, "count": len(rows), "extensions": rows},
                    ensure_ascii=False,
                    indent=2,
                )
            if action == "registered":
                from core.extensions.agent_registry import (
                    agent_extension_settings,
                    agent_slash_commands,
                )

                settings = agent_extension_settings(profile)
                slashes = [
                    {"command": s.command, "description": s.description}
                    for s in agent_slash_commands()
                ]
                return json.dumps(
                    {
                        "profile": profile,
                        "loaded_settings": settings,
                        "slash_commands_from_extensions": slashes,
                        "note": (
                            "After create/enable the current agent hot-reloads automatically "
                            "(local mode). Messenger bots require process restart."
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            if action == "show_control":
                from core.extensions.control import control_path, load_control

                return json.dumps(
                    {
                        "profile": profile,
                        "control_file": str(control_path(profile)),
                        "control": load_control(profile),
                        "env_kill_switch": "HOLIX_AGENT_EXTENSIONS_OFF=1",
                        "env_disable_list": "HOLIX_AGENT_EXTENSIONS_DISABLED=name1,name2",
                        "self_extensions": (
                            "allowed" if _self_ext_allowed(self._agent) else "denied"
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            if action == "reload":
                if not _self_ext_allowed(self._agent):
                    from core.extensions.self_ext_policy import self_extension_denied_message

                    return json.dumps(
                        {
                            "ok": False,
                            "error": "self_extensions_denied",
                            "message": self_extension_denied_message(),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                result = _hot_reload(self._agent)
                return json.dumps(
                    {"ok": True, "action": "reload", "hot_reload": result},
                    ensure_ascii=False,
                    indent=2,
                )
            if action == "create":
                from core.extensions.scaffold import create_agent_extension_scaffold

                result = create_agent_extension_scaffold(
                    profile,
                    name,
                    description=description,
                    overwrite=bool(overwrite),
                )
                hot = _hot_reload(self._agent)
                payload: dict[str, Any] = {
                    "ok": True,
                    **result,
                    "hot_reload": hot,
                }
                if hot and hot.get("ok") is not False:
                    payload["next"] = (
                        "Extension scaffolded and hot-reloaded into this session. "
                        "Edit agent.py if needed, then call "
                        "manage_agent_extensions(action=reload) to pick up code changes. "
                        "Test the new tool / slash command now."
                    )
                else:
                    payload["next"] = (
                        "Scaffold created but hot-reload failed or agent is unavailable. "
                        "Start a new agent session so the extension is discovered."
                    )
                return json.dumps(payload, ensure_ascii=False, indent=2)
            if action == "disable":
                from core.extensions.control import disable_extension

                result = disable_extension(
                    profile, name, reason=reason or "disabled via manage_agent_extensions"
                )
                hot = None
                if _self_ext_allowed(self._agent):
                    hot = _hot_reload(self._agent)
                return json.dumps(
                    {
                        "ok": True,
                        **result,
                        "hot_reload": hot,
                        "next": (
                            "Extension disabled and unloaded from this session."
                            if hot and hot.get("ok") is not False
                            else "Disabled. Restart agent/bot if tools still appear."
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            if action == "enable":
                from core.extensions.control import enable_extension

                result = enable_extension(profile, name)
                hot = _hot_reload(self._agent)
                return json.dumps(
                    {
                        "ok": True,
                        **result,
                        "hot_reload": hot,
                        "next": (
                            "Extension enabled and loaded into this session."
                            if hot and hot.get("ok") is not False
                            else "Enabled. Reload agent if tools are missing."
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            if action == "quarantine_clear":
                from core.extensions.control import clear_quarantine, enable_extension

                q = clear_quarantine(profile, name)
                e = enable_extension(profile, name)
                hot = _hot_reload(self._agent)
                return json.dumps(
                    {
                        "ok": True,
                        "quarantine": q,
                        "enable": e,
                        "hot_reload": hot,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            return json.dumps({"ok": False, "error": f"unknown action: {action}"})
        except Exception as exc:
            return json.dumps(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                ensure_ascii=False,
            )


def register_agent_extension_manager_tool(agent: Any) -> None:
    """Attach manage_agent_extensions to the agent tool registry."""
    try:
        agent.tools.register(ManageAgentExtensionsTool(agent))
    except Exception:
        pass
