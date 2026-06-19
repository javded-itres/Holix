"""Canonical tool names and backward-compatible aliases."""

from __future__ import annotations

import copy
from typing import Any

TOOL_ALIASES: dict[str, str] = {
    "web_fetch": "fetch_url",
    "run_project": "start_background_process",
}


def resolve_tool_name(name: str) -> str:
    return TOOL_ALIASES.get(name, name)


def get_registered_tool(registry: Any, name: str) -> Any | None:
    tools = getattr(registry, "tools", None)
    if not isinstance(tools, dict):
        return None
    return tools.get(resolve_tool_name(name)) or tools.get(name)


def tool_schema_for_name(tool: Any, exposed_name: str) -> dict[str, Any]:
    """Return an OpenAI tool schema, optionally under an alias name."""
    schema = tool.to_openai_schema()
    canonical = getattr(tool, "name", exposed_name)
    if exposed_name != canonical:
        schema = copy.deepcopy(schema)
        schema["function"]["name"] = exposed_name
    return schema