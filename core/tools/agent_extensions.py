"""Agent tools to list / scaffold / enable / disable drop-in agent extensions."""

from __future__ import annotations

import json
from typing import Any

from core.tools.base import BaseTool

# Operator-only on Telegram/MAX (bot admin); local CLI/TUI always allowed.
_OPERATOR_ACTIONS = frozenset(
    {
        "create",
        "disable",
        "enable",
        "quarantine_clear",
        "reload",
        "show_control",
        "settings_get",
        "settings_set",
    }
)
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
            "Manage Holix agent extensions and their system settings (profile folder, not core). "
            "Actions: list, registered, create, disable, enable, quarantine_clear, "
            "show_control, reload, settings_get, settings_set. "
            "On Telegram/MAX only the **bot admin** may create/enable/disable/reload "
            "or change extension settings. Regular users may only list/registered. "
            "Local CLI/TUI is the operator. After create, hot-reload tools in this session. "
            "Emergency: HOLIX_AGENT_EXTENSIONS_OFF=1."
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
                        "settings_get",
                        "settings_set",
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
                "settings": {
                    "type": "object",
                    "description": "JSON object to merge (settings_set)",
                    "additionalProperties": True,
                },
                "replace": {
                    "type": "boolean",
                    "description": "settings_set: replace file instead of merge",
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
        settings: dict[str, Any] | None = None,
        replace: bool = False,
        **kwargs: Any,
    ) -> str:
        profile = _profile(self._agent)
        action = (action or "list").strip().lower()
        try:
            if action in _OPERATOR_ACTIONS and not _self_ext_allowed(self._agent):
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
            if action == "settings_get":
                from core.extensions.settings import (
                    extension_settings_path,
                    load_extension_settings,
                )

                ext = (name or "").strip()
                if not ext:
                    return json.dumps(
                        {"ok": False, "error": "name is required for settings_get"},
                        ensure_ascii=False,
                    )
                data = load_extension_settings(profile, ext)
                return json.dumps(
                    {
                        "ok": True,
                        "profile": profile,
                        "extension": ext,
                        "settings_file": str(extension_settings_path(profile, ext)),
                        "settings": data,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            if action == "settings_set":
                from core.extensions.settings import (
                    extension_settings_path,
                    load_extension_settings,
                    merge_extension_settings,
                    save_extension_settings,
                )

                ext = (name or "").strip()
                patch = settings if isinstance(settings, dict) else {}
                if not ext:
                    return json.dumps(
                        {"ok": False, "error": "name is required for settings_set"},
                        ensure_ascii=False,
                    )
                if not patch and not replace:
                    return json.dumps(
                        {"ok": False, "error": "settings object is required for settings_set"},
                        ensure_ascii=False,
                    )
                current = {} if replace else load_extension_settings(profile, ext)
                merged = patch if replace else merge_extension_settings(current, patch)
                path = save_extension_settings(profile, ext, merged)
                hot = _hot_reload(self._agent)
                return json.dumps(
                    {
                        "ok": True,
                        "profile": profile,
                        "extension": ext,
                        "settings_file": str(path),
                        "settings": merged,
                        "hot_reload": hot,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            if action == "reload":
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
