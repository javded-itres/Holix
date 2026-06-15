"""Helpers for preparing sub-agent spawn configuration."""

from __future__ import annotations

from typing import Any

from core.platform_compat import process_subagents_supported
from core.subagents.base import ProcessMode, SubAgentConfig
from core.subagents.registry import get_subagent_config


def _inject_external_cli_tools(
    agent_type: str,
    profile: str,
    tools: list[str],
) -> list[str]:
    from core.external_cli.access import subagent_has_external_cli_assignment
    from core.external_cli.platform import launch_supported

    if not launch_supported():
        return tools
    if not subagent_has_external_cli_assignment(profile, agent_type):
        return tools
    out = list(tools)
    if "external_cli" not in out:
        out.append("external_cli")
    return out


def resolve_process_mode(parent_config: Any) -> ProcessMode:
    """Pick async vs OS-process mode from parent runtime config."""
    raw = str(
        getattr(parent_config, "subagent_default_process_mode", "process") or "process"
    ).lower()
    if raw == "process" and process_subagents_supported():
        return ProcessMode.PROCESS
    return ProcessMode.ASYNC


def prepare_subagent_config(
    agent_type: str,
    parent_config: Any,
    *,
    instance_name: str,
) -> SubAgentConfig:
    """Build a spawn-ready config with process mode and unique instance name."""
    profile = str(getattr(parent_config, "profile_name", None) or "default")
    cfg = get_subagent_config(agent_type, profile=profile)
    cfg.name = instance_name
    cfg.agent_type = agent_type
    cfg.process_mode = resolve_process_mode(parent_config)
    timeout = getattr(parent_config, "subagent_process_timeout", None)
    if timeout:
        cfg.timeout = float(timeout)

    mcp_assigns = getattr(parent_config, "mcp_assignments", None) or {}
    if not cfg.mcp_servers and agent_type in mcp_assigns:
        cfg.mcp_servers = list(mcp_assigns[agent_type])

    from core.subagents.store import SubAgentTypeStore

    custom = SubAgentTypeStore(profile).get(agent_type)
    if custom and custom.model_slot:
        try:
            from core.models.manager import ModelManager

            mc = ModelManager(parent_config).get_agent_model_config(custom.model_slot)
            if mc:
                cfg.model = mc.model
        except Exception:
            pass

    tools = list(cfg.tools or [])
    if "ask_user" not in tools:
        tools.append("ask_user")
    cfg.tools = _inject_external_cli_tools(agent_type, profile, tools)
    return cfg