"""Helpers for preparing sub-agent spawn configuration."""

from __future__ import annotations

from typing import Any

from core.platform_compat import process_subagents_supported
from core.subagents.base import ProcessMode, SubAgentConfig
from core.subagents.registry import get_subagent_config


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
    cfg = get_subagent_config(agent_type)
    cfg.name = instance_name
    cfg.process_mode = resolve_process_mode(parent_config)
    timeout = getattr(parent_config, "subagent_process_timeout", None)
    if timeout:
        cfg.timeout = float(timeout)
    tools = list(cfg.tools or [])
    if "ask_user" not in tools:
        tools.append("ask_user")
    cfg.tools = tools
    return cfg