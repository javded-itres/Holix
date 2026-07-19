"""Agent extension entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from holix_sdk.agent import SlashCommandSpec

from holix_extension_demo.middleware import RequestStatsMiddleware
from holix_extension_demo.tool import DemoEchoTool

try:
    from core.extensions.agent_base import AgentExtensionBase
except ImportError:
    from holix_sdk.agent import AgentExtensionBase  # type: ignore[no-redef]


class DemoAgentExtension(AgentExtensionBase):
    name = "demo"
    version = "0.1.0"
    requires_holix = ">=0.1.21"
    permissions = frozenset({"tools", "middleware"})

    def default_settings(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "collect_stats": True,
            "stats_filename": "demo_llm_stats.jsonl",
        }

    def on_settings_loaded(self, settings: dict[str, Any]) -> None:
        self.settings = dict(settings or {})

    def register_tools(self, registry: Any, agent: Any) -> None:
        registry.register(DemoEchoTool())

    def register_slash_commands(self, commands: list[SlashCommandSpec]) -> None:
        commands.append(SlashCommandSpec(command="/demo", description="Holix extension demo command"))

    def augment_system_prompt(self, profile: str) -> str | None:
        return (
            "## Extension demo\n"
            "The `demo_echo` tool is available from holix-extension-demo. "
            "LLM request stats middleware is optional (settings.collect_stats)."
        )

    def register_middleware(self, chain: Any, agent: Any) -> None:
        settings = getattr(self, "settings", {}) or {}
        if settings.get("collect_stats") is False:
            return
        data_dir = getattr(getattr(agent, "config", None), "data_dir", None) or "."
        filename = str(settings.get("stats_filename") or "demo_llm_stats.jsonl")
        path = Path(data_dir) / "extensions" / "demo" / filename
        chain.add(RequestStatsMiddleware(path=path, enabled=True))


def get_agent_extension() -> DemoAgentExtension:
    return DemoAgentExtension()
