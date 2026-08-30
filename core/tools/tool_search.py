"""Discover builtin / MCP / skill / extension tools by name or description."""

from __future__ import annotations

import re
from typing import Any

from core.tools.base import BaseTool
from core.tools.execution_context import get_agent_slot, get_profile_name, get_tools_registry
from core.tools.result import tool_err, tool_ok
from core.tools.slot_policy import tool_allowed_for_slot


def _score(query: str, name: str, description: str) -> int:
    q = query.lower().strip()
    if not q:
        return 0
    blob = f"{name} {description}".lower()
    score = 0
    if q in name.lower():
        score += 8
    if q in blob:
        score += 4
    for token in re.split(r"\s+", q):
        if token and token in blob:
            score += 1
    return score


def _first_paragraph(text: str) -> str:
    body = (text or "").strip()
    if not body:
        return ""
    parts = re.split(r"\n\s*\n", body, maxsplit=1)
    line = parts[0].replace("\n", " ").strip()
    return line[:240]


class ToolSearchTool(BaseTool):
    """Search names+descriptions of builtin, MCP, skill, and extension tools."""

    def __init__(self) -> None:
        super().__init__()
        self.name = "tool_search"
        self.description = (
            "Search Holix tools that are not in the current tools list "
            "(MCP, browser, SDD, SQL, notebook, jobs, session search, …), "
            "plus skills and extensions, by name or description. "
            "If a tool name is missing, call this instead of inventing a name. "
            "enable_matches=true (default) attaches top hits to this session "
            "so you can call them on the next step (slot allowlist still applies)."
        )
        self.risk_level = "no"
        self.parameters = {
            "type": "object",
            "additionalProperties": False,
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 8,
                },
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["builtin", "mcp", "skill", "extension"],
                    },
                },
                "enable_matches": {
                    "type": "boolean",
                    "default": True,
                    "description": "Attach top hits to this session's tools list (default true).",
                },
            },
        }

    async def execute(
        self,
        query: str,
        limit: int = 8,
        sources: list[str] | None = None,
        enable_matches: bool = True,
        **_: Any,
    ) -> str:
        q = (query or "").strip()
        if not q:
            return tool_err("missing_query", "query is required")
        limit = max(1, min(int(limit or 8), 20))
        wanted = {str(s).strip().lower() for s in (sources or []) if str(s).strip()}
        if not wanted:
            wanted = {"builtin", "mcp", "skill", "extension"}

        registry = get_tools_registry()
        slot = get_agent_slot()
        active: set[str] = set()
        catalog: list[dict[str, Any]] = []
        seen: set[str] = set()

        if registry is not None:
            try:
                schemas = registry.get_end_tool_schemas(for_agent_slot=slot)
            except Exception:
                schemas = []
            for schema in schemas:
                fn = schema.get("function") if isinstance(schema, dict) else None
                if isinstance(fn, dict) and fn.get("name"):
                    active.add(str(fn["name"]))

            tools = getattr(registry, "tools", {}) or {}
            for name, tool in tools.items():
                canonical = str(getattr(tool, "name", "") or name)
                if not canonical or canonical in seen:
                    continue
                seen.add(canonical)
                source = "mcp" if canonical.startswith("mcp_") else "builtin"
                if source not in wanted:
                    continue
                desc = str(getattr(tool, "description", "") or "")
                catalog.append(
                    {
                        "name": canonical,
                        "description": desc[:240],
                        "source": source,
                        "enabled": canonical in active,
                    }
                )

        if "skill" in wanted:
            catalog.extend(_skill_entries())
        if "extension" in wanted:
            catalog.extend(_extension_entries())

        ranked: list[tuple[int, dict[str, Any]]] = []
        for item in catalog:
            score = _score(q, str(item.get("name") or ""), str(item.get("description") or ""))
            if score <= 0:
                continue
            ranked.append((score, item))
        ranked.sort(key=lambda pair: (-pair[0], str(pair[1].get("name") or "")))
        matches = [item for _, item in ranked[:limit]]

        if enable_matches and registry is not None:
            extra = getattr(registry, "_session_enabled_tools", None)
            if extra is None:
                extra = set()
                registry._session_enabled_tools = extra
            for item in matches:
                name = str(item.get("name") or "")
                if not name or not tool_allowed_for_slot(name, slot):
                    continue
                if str(item.get("source") or "") == "skill":
                    continue
                extra.add(name)
                if name in getattr(registry, "tools", {}):
                    item["enabled"] = True

        return tool_ok(matches=matches)


def _skill_entries() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
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
        for name, skill in (mgr.all_skills or {}).items():
            desc = str(skill.get("description") or "")
            body = str(skill.get("content") or skill.get("body") or "")
            if not desc:
                desc = _first_paragraph(body)
            out.append(
                {
                    "name": str(name),
                    "description": desc[:240],
                    "source": "skill",
                    "enabled": False,
                }
            )
    except Exception:
        return out
    return out


def _extension_entries() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        from core.extensions.registry import list_extension_info

        for info in list_extension_info() or []:
            name = str(getattr(info, "name", "") or "")
            if not name:
                continue
            out.append(
                {
                    "name": name,
                    "description": str(getattr(info, "description", "") or "")[:240],
                    "source": "extension",
                    "enabled": False,
                }
            )
    except Exception:
        return out
    return out
