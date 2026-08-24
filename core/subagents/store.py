"""Per-profile custom sub-agent type definitions."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Self

from core.profile.names import profile_dir_for_name, validate_profile_name
from core.subagents.base import SubAgentConfig
from core.subagents.registry import builtin_subagent_names

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")

SUBAGENT_TOOL_CHOICES: tuple[str, ...] = (
    "read_file",
    "write_file",
    "patch_file",
    "list_directory",
    "grep",
    "glob",
    "delete_file",
    "terminal",
    "web_search",
    "web_fetch",
    "code_executor",
    "math_calculator",
    "sql_query",
    "sql_schema",
    "sdd_status",
    "sdd_write_artifact",
    "sdd_update_spec",
    "todo_write",
)

DEFAULT_CUSTOM_TOOLS: list[str] = ["read_file", "list_directory", "grep", "glob", "terminal"]


def subagents_dir(profile: str) -> Path:
    return (profile_dir_for_name(profile) / "subagents").resolve()


def types_path(profile: str) -> Path:
    return subagents_dir(profile) / "types.json"


@dataclass(slots=True)
class CustomSubAgentType:
    name: str
    description: str = ""
    system_prompt: str = ""
    tools: list[str] = field(default_factory=lambda: list(DEFAULT_CUSTOM_TOOLS))
    max_steps: int = 150
    temperature: float = 0.3
    skills: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)
    skills_inherit: bool = True
    mcp_inherit: bool = True
    model_slot: str = ""
    external_cli_id: str = ""
    tools_presentation: str = ""  # native|code|both; empty = inherit profile

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        tools = [str(t) for t in (data.get("tools") or DEFAULT_CUSTOM_TOOLS) if str(t).strip()]
        return cls(
            name=str(data["name"]).strip().lower(),
            description=str(data.get("description") or ""),
            system_prompt=str(data.get("system_prompt") or ""),
            tools=tools or list(DEFAULT_CUSTOM_TOOLS),
            max_steps=int(data.get("max_steps") or 150),
            temperature=float(
                data.get("temperature") if data.get("temperature") is not None else 0.3
            ),
            skills=[str(s) for s in (data.get("skills") or []) if str(s).strip()],
            mcp_servers=[str(m) for m in (data.get("mcp_servers") or []) if str(m).strip()],
            skills_inherit=bool(data.get("skills_inherit", True)),
            mcp_inherit=bool(data.get("mcp_inherit", True)),
            model_slot=str(data.get("model_slot") or ""),
            external_cli_id=str(data.get("external_cli_id") or ""),
            tools_presentation=str(data.get("tools_presentation") or "").strip().lower(),
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
        self.profile = validate_profile_name(profile)
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


def resolve_model_slot_binding(profile: str, model_slot: str) -> tuple[str, str] | None:
    """Map a Studio/CLI model slot id to (provider, model).

    Empty / main / inherit → None (use parent main agent model).
    """
    slot = (model_slot or "").strip()
    if not slot or slot.lower() in ("main", "default", "inherit", "parent"):
        return None
    try:
        from core.models.menu import build_models_menu

        menu = build_models_menu(profile)
        for preset in menu.presets:
            if preset.slot_id == slot:
                return str(preset.provider), str(preset.model)
        for prov in menu.providers:
            prefix = f"prov:{prov.name}:"
            if slot.startswith(prefix):
                model_id = slot[len(prefix) :]
                # Accept even if not currently in available_models (menu may be
                # filtered later); the slot id is the source of truth.
                if model_id:
                    return str(prov.name), str(model_id)
    except Exception:
        pass
    if slot.startswith("prov:"):
        parts = slot.split(":", 2)
        if len(parts) == 3 and parts[1] and parts[2]:
            return parts[1], parts[2]
    return None


def sync_custom_type_profile_bindings(
    profile: str,
    custom: CustomSubAgentType,
    *,
    previous_name: str | None = None,
) -> None:
    """Persist skills, MCP, model slot, and external CLI links for a custom type."""
    from core.external_cli.assignment import assign_cli_to_subagent, unassign_cli_subagent
    from core.external_cli.store import ExternalCliStore
    from core.profile import get_profile_manager

    manager = get_profile_manager()
    config = manager.load_profile(profile)
    agent_slot = custom.name

    if previous_name and previous_name != agent_slot:
        old_assigns = dict(getattr(config, "skill_assignments", None) or {})
        if previous_name in old_assigns:
            del old_assigns[previous_name]
            config.skill_assignments = old_assigns
        old_mcp = dict(getattr(config, "mcp_assignments", None) or {})
        if previous_name in old_mcp:
            del old_mcp[previous_name]
            config.mcp_assignments = old_mcp

    assigns = dict(getattr(config, "skill_assignments", None) or {})
    explicit_skills = list(dict.fromkeys(custom.skills))
    if getattr(custom, "skills_inherit", True) and not explicit_skills:
        assigns.pop(agent_slot, None)
    else:
        assigns[agent_slot] = explicit_skills
    config.skill_assignments = assigns

    mcp_assigns = dict(getattr(config, "mcp_assignments", None) or {})
    explicit_mcp = list(dict.fromkeys(custom.mcp_servers))
    if getattr(custom, "mcp_inherit", True) and not explicit_mcp:
        mcp_assigns.pop(agent_slot, None)
    else:
        mcp_assigns[agent_slot] = explicit_mcp
    config.mcp_assignments = mcp_assigns

    model_slot = (custom.model_slot or "").strip()
    agent_models = dict(getattr(config, "agent_models", None) or {})
    if model_slot and model_slot.lower() not in ("main", "default", "inherit", "parent"):
        resolved = resolve_model_slot_binding(profile, model_slot)
        if resolved:
            entry = {
                "provider": resolved[0],
                "model": resolved[1],
            }
            # Slot id (prov:litellm:…) and type name both map to the same model
            # so spawn can resolve via either path.
            agent_models[model_slot] = entry
            agent_models[agent_slot] = entry
            config.agent_models = agent_models
    else:
        # Inherit main: drop previous type-level override if present.
        if agent_slot in agent_models and agent_slot != "main":
            del agent_models[agent_slot]
            config.agent_models = agent_models

    manager.save_profile(profile, config)

    store = ExternalCliStore(profile)
    bindings = store.load_bindings()
    for binding in bindings.values():
        if binding.agent_slot == agent_slot and binding.cli_id != custom.external_cli_id:
            binding.agent_slot = ""
            store.upsert_binding(binding)

    if custom.external_cli_id:
        assign_cli_to_subagent(profile, custom.external_cli_id, agent_slot)
    else:
        for cli_id, binding in bindings.items():
            if binding.agent_slot == agent_slot:
                unassign_cli_subagent(profile, cli_id)


def cleanup_custom_type_profile_bindings(profile: str, name: str) -> None:
    """Remove profile links when a custom sub-agent type is deleted."""
    from core.profile import get_profile_manager

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


def overlays_path(profile: str) -> Path:
    return subagents_dir(profile) / "overlays.json"


@dataclass(slots=True)
class TypeOverlay:
    """Per-type overrides for built-in (and custom) sub-agents."""

    system_prompt: str | None = None
    description: str | None = None
    temperature: float | None = None
    model_slot: str | None = None
    tools_presentation: str | None = None
    tools: list[str] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        temp = data.get("temperature")
        try:
            temperature = float(temp) if temp is not None and str(temp).strip() != "" else None
        except (TypeError, ValueError):
            temperature = None
        pres = str(data.get("tools_presentation") or "").strip().lower() or None
        if pres not in ("native", "code", "both"):
            pres = None
        model_slot = str(data.get("model_slot") or "").strip() or None
        prompt = str(data.get("system_prompt") or "")
        desc = str(data.get("description") or "")
        tools: list[str] | None = None
        if "tools" in data and data.get("tools") is not None:
            tools = [str(item).strip() for item in data.get("tools") or [] if str(item).strip()]
        return cls(
            system_prompt=prompt or None,
            description=desc or None,
            temperature=temperature,
            model_slot=model_slot,
            tools_presentation=pres,
            tools=tools,
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.system_prompt:
            out["system_prompt"] = self.system_prompt
        if self.description:
            out["description"] = self.description
        if self.temperature is not None:
            out["temperature"] = self.temperature
        if self.model_slot:
            out["model_slot"] = self.model_slot
        if self.tools_presentation:
            out["tools_presentation"] = self.tools_presentation
        if self.tools is not None:
            out["tools"] = list(self.tools)
        return out

    def is_empty(self) -> bool:
        return not self.to_dict()


class SubAgentOverlayStore:
    def __init__(self, profile: str) -> None:
        self.profile = validate_profile_name(profile)
        subagents_dir(profile).mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, TypeOverlay]:
        path = overlays_path(self.profile)
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        items = raw.get("overlays") if isinstance(raw, dict) else raw
        if not isinstance(items, dict):
            return {}
        out: dict[str, TypeOverlay] = {}
        for key, item in items.items():
            if not isinstance(item, dict):
                continue
            slug = str(key).strip().lower()
            if not slug:
                continue
            overlay = TypeOverlay.from_dict(item)
            if not overlay.is_empty():
                out[slug] = overlay
        return out

    def get(self, name: str) -> TypeOverlay | None:
        return self.load().get((name or "").strip().lower())

    def upsert(self, name: str, overlay: TypeOverlay) -> TypeOverlay:
        slug = (name or "").strip().lower()
        if not slug:
            raise ValueError("Type name is required")
        items = self.load()
        if overlay.is_empty():
            items.pop(slug, None)
        else:
            items[slug] = overlay
        self._save(items)
        return overlay

    def merge(self, name: str, **fields: Any) -> TypeOverlay:
        current = self.get(name) or TypeOverlay()
        data = current.to_dict()
        for key, value in fields.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        overlay = TypeOverlay.from_dict(data)
        return self.upsert(name, overlay)

    def remove(self, name: str) -> bool:
        slug = (name or "").strip().lower()
        items = self.load()
        if slug not in items:
            return False
        del items[slug]
        self._save(items)
        return True

    def _save(self, items: dict[str, TypeOverlay]) -> None:
        payload = {
            "overlays": {k: v.to_dict() for k, v in sorted(items.items()) if not v.is_empty()}
        }
        overlays_path(self.profile).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def apply_type_overlay(cfg: SubAgentConfig, overlay: TypeOverlay | None) -> SubAgentConfig:
    if overlay is None:
        return cfg
    if overlay.system_prompt:
        cfg.system_prompt = overlay.system_prompt
    if overlay.description:
        cfg.description = overlay.description
    if overlay.temperature is not None:
        cfg.temperature = float(overlay.temperature)
    if overlay.tools is not None:
        cfg.tools = list(overlay.tools)
    return cfg
