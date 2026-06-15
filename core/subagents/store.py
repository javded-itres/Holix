"""Per-profile custom sub-agent type definitions."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Self

from core.platform_compat import resolve_holix_home
from core.subagents.base import SubAgentConfig
from core.subagents.registry import PREDEFINED_SUBAGENTS, builtin_subagent_names

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")

SUBAGENT_TOOL_CHOICES: tuple[str, ...] = (
    "read_file",
    "write_file",
    "list_directory",
    "terminal",
    "web_search",
    "web_fetch",
    "code_executor",
    "math_calculator",
    "sql_query",
    "sql_schema",
)

DEFAULT_CUSTOM_TOOLS: list[str] = ["read_file", "list_directory", "terminal"]


def subagents_dir(profile: str) -> Path:
    return (resolve_holix_home() / "profiles" / profile / "subagents").resolve()


def types_path(profile: str) -> Path:
    return subagents_dir(profile) / "types.json"


@dataclass(slots=True)
class CustomSubAgentType:
    name: str
    description: str = ""
    system_prompt: str = ""
    tools: list[str] = field(default_factory=lambda: list(DEFAULT_CUSTOM_TOOLS))
    max_steps: int = 12
    temperature: float = 0.3
    skills: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)
    model_slot: str = ""
    external_cli_id: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        tools = [str(t) for t in (data.get("tools") or DEFAULT_CUSTOM_TOOLS) if str(t).strip()]
        return cls(
            name=str(data["name"]).strip().lower(),
            description=str(data.get("description") or ""),
            system_prompt=str(data.get("system_prompt") or ""),
            tools=tools or list(DEFAULT_CUSTOM_TOOLS),
            max_steps=int(data.get("max_steps") or 12),
            temperature=float(data.get("temperature") if data.get("temperature") is not None else 0.3),
            skills=[str(s) for s in (data.get("skills") or []) if str(s).strip()],
            mcp_servers=[str(m) for m in (data.get("mcp_servers") or []) if str(m).strip()],
            model_slot=str(data.get("model_slot") or ""),
            external_cli_id=str(data.get("external_cli_id") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_subagent_config(self) -> SubAgentConfig:
        return SubAgentConfig(
            name=self.name,
            agent_type=self.name,
            system_prompt=self.system_prompt,
            tools=list(self.tools),
            max_steps=self.max_steps,
            temperature=self.temperature,
            description=self.description,
            mcp_servers=list(self.mcp_servers),
            tags=["custom"],
        )


def validate_custom_type_name(name: str) -> str:
    slug = (name or "").strip().lower()
    if not slug:
        raise ValueError("Sub-agent type name is required")
    if not _NAME_RE.match(slug):
        raise ValueError(
            "Name must be 2–48 chars: lowercase letters, digits, hyphen, underscore; start with a letter"
        )
    if slug in builtin_subagent_names():
        raise ValueError(f"Name '{slug}' is reserved for a built-in sub-agent type")
    return slug


class SubAgentTypeStore:
    def __init__(self, profile: str) -> None:
        self.profile = profile
        subagents_dir(profile).mkdir(parents=True, exist_ok=True)

    def load_types(self) -> dict[str, CustomSubAgentType]:
        path = types_path(self.profile)
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        items = raw.get("types") if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return {}
        out: dict[str, CustomSubAgentType] = {}
        for item in items:
            if not isinstance(item, dict) or "name" not in item:
                continue
            try:
                custom = CustomSubAgentType.from_dict(item)
                out[custom.name] = custom
            except Exception:
                continue
        return out

    def save_types(self, types: dict[str, CustomSubAgentType]) -> None:
        data = {"types": [t.to_dict() for t in sorted(types.values(), key=lambda x: x.name)]}
        types_path(self.profile).write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def get(self, name: str) -> CustomSubAgentType | None:
        return self.load_types().get((name or "").strip().lower())

    def upsert(self, custom: CustomSubAgentType) -> CustomSubAgentType:
        custom.name = validate_custom_type_name(custom.name)
        types = self.load_types()
        types[custom.name] = custom
        self.save_types(types)
        return custom

    def remove(self, name: str) -> CustomSubAgentType | None:
        slug = (name or "").strip().lower()
        types = self.load_types()
        removed = types.pop(slug, None)
        if removed is None:
            return None
        self.save_types(types)
        return removed


def sync_custom_type_profile_bindings(
    profile: str,
    custom: CustomSubAgentType,
    *,
    previous_name: str | None = None,
) -> None:
    """Persist skills, MCP, model slot, and external CLI links for a custom type."""
    from cli.core import get_profile_manager
    from core.external_cli.assignment import assign_cli_to_subagent, unassign_cli_subagent
    from core.external_cli.store import ExternalCliStore
    manager = get_profile_manager()
    config = manager.load_profile(profile)
    slot = custom.name

    if previous_name and previous_name != slot:
        old_assigns = dict(getattr(config, "skill_assignments", None) or {})
        if previous_name in old_assigns:
            del old_assigns[previous_name]
            config.skill_assignments = old_assigns
        old_mcp = dict(getattr(config, "mcp_assignments", None) or {})
        if previous_name in old_mcp:
            del old_mcp[previous_name]
            config.mcp_assignments = old_mcp

    assigns = dict(getattr(config, "skill_assignments", None) or {})
    if custom.skills:
        assigns[slot] = list(dict.fromkeys(custom.skills))
    elif slot in assigns:
        del assigns[slot]
    config.skill_assignments = assigns

    mcp_assigns = dict(getattr(config, "mcp_assignments", None) or {})
    if custom.mcp_servers:
        mcp_assigns[slot] = list(dict.fromkeys(custom.mcp_servers))
    elif slot in mcp_assigns:
        del mcp_assigns[slot]
    config.mcp_assignments = mcp_assigns

    if custom.model_slot:
        agent_models = dict(getattr(config, "agent_models", None) or {})
        if custom.model_slot not in agent_models and custom.model_slot != "main":
            from integrations.telegram.model_switch import build_models_menu

            menu = build_models_menu(profile)
            for preset in menu.presets:
                if preset.slot_id == custom.model_slot:
                    agent_models[custom.model_slot] = {
                        "provider": preset.provider,
                        "model": preset.model,
                    }
                    break
        config.agent_models = agent_models

    manager.save_profile(profile, config)

    store = ExternalCliStore(profile)
    bindings = store.load_bindings()
    for binding in bindings.values():
        if binding.agent_slot == slot and binding.cli_id != custom.external_cli_id:
            binding.agent_slot = ""
            store.upsert_binding(binding)

    if custom.external_cli_id:
        assign_cli_to_subagent(profile, custom.external_cli_id, slot)
    else:
        for cli_id, binding in bindings.items():
            if binding.agent_slot == slot:
                unassign_cli_subagent(profile, cli_id)


def cleanup_custom_type_profile_bindings(profile: str, name: str) -> None:
    """Remove profile links when a custom sub-agent type is deleted."""
    from cli.core import get_profile_manager

    manager = get_profile_manager()
    config = manager.load_profile(profile)
    slot = (name or "").strip().lower()

    assigns = dict(getattr(config, "skill_assignments", None) or {})
    if slot in assigns:
        del assigns[slot]
        config.skill_assignments = assigns

    mcp_assigns = dict(getattr(config, "mcp_assignments", None) or {})
    if slot in mcp_assigns:
        del mcp_assigns[slot]
        config.mcp_assignments = mcp_assigns

    manager.save_profile(profile, config)

    from core.external_cli.store import ExternalCliStore

    store = ExternalCliStore(profile)
    for binding in store.load_bindings().values():
        if binding.agent_slot == slot:
            binding.agent_slot = ""
            store.upsert_binding(binding)