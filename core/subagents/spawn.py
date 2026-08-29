"""Helpers for preparing sub-agent spawn configuration."""

from __future__ import annotations

import logging
from typing import Any

from core.platform_compat import prefer_async_subagents, process_subagents_supported
from core.subagents.base import ProcessMode, SubAgentConfig
from core.subagents.registry import get_subagent_config

logger = logging.getLogger(__name__)


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
    raw = str(getattr(parent_config, "subagent_default_process_mode", "async") or "async").lower()
    if raw == "process" and process_subagents_supported() and not prefer_async_subagents():
        return ProcessMode.PROCESS
    return ProcessMode.ASYNC


def resolve_subagent_model_id(
    parent_config: Any,
    profile: str,
    model_slot: str,
) -> str | None:
    """Resolve a Studio/CLI model slot to a concrete model id for sub-agent spawn.

    Empty / main / inherit → None (caller keeps parent model).

    Important: do **not** use ``ModelManager.get_agent_model_config(slot)`` when
    ``slot`` is missing from ``agent_models`` — that helper falls back to the
    profile default (e.g. smart), so Studio ``prov:litellm:…`` picks never apply.
    """
    slot = (model_slot or "").strip()
    if not slot or slot.lower() in ("main", "default", "inherit", "parent"):
        return None

    from core.models.manager import ModelManager
    from core.subagents.store import resolve_model_slot_binding

    mm = ModelManager(parent_config)
    agent_models = getattr(parent_config, "agent_models", None) or {}

    # 1) Explicit agent_models entry for this slot (only when key exists).
    if slot in agent_models:
        try:
            mc = mm.get_agent_model_config(slot)
            if mc and (mc.model or "").strip():
                return str(mc.model).strip()
        except Exception:
            logger.debug("agent_models lookup failed for slot %r", slot, exc_info=True)

    # 2) Studio provider slots and named presets (reads profile menu from disk).
    binding = resolve_model_slot_binding(profile, slot)
    if binding:
        provider, model_id = binding
        try:
            pmc = mm.get_provider_model_config(provider, model_id=model_id)
            if pmc and (pmc.model or "").strip():
                return str(pmc.model).strip()
        except Exception:
            logger.debug(
                "provider model config failed for %s/%s",
                provider,
                model_id,
                exc_info=True,
            )
        if model_id:
            return str(model_id).strip()

    # 3) Bare model id already (e.g. "kimi-k2.7-code") if known on a provider.
    providers = getattr(parent_config, "providers", None) or {}
    for pname, pdata in providers.items():
        if not isinstance(pdata, dict):
            continue
        available = pdata.get("available_models") or []
        default_model = pdata.get("default_model") or ""
        if slot == default_model or slot in available:
            try:
                pmc = mm.get_provider_model_config(pname, model_id=slot)
                if pmc and (pmc.model or "").strip():
                    return str(pmc.model).strip()
            except Exception:
                pass
            return slot

    logger.warning(
        "Could not resolve sub-agent model_slot %r for profile %r — inheriting parent model",
        slot,
        profile,
    )
    return None


def spawn_model_slot(
    agent_type: str,
    parent_config: Any,
    profile: str,
) -> str:
    """Which ``agent_models`` / Studio slot to use when spawning this type.

    Custom type ``model_slot`` wins (including ``main`` / ``inherit`` → parent).
    Otherwise, if the profile has ``agent_models.<type>`` (built-in ``coder``,
    …), use that slot. Empty means inherit the parent model.
    """
    from core.subagents.store import SubAgentOverlayStore, SubAgentTypeStore

    overlay = SubAgentOverlayStore(profile).get(agent_type)
    if overlay is not None and (overlay.model_slot or "").strip():
        return str(overlay.model_slot).strip()
    custom = SubAgentTypeStore(profile).get(agent_type)
    if custom is not None:
        raw = (custom.model_slot or "").strip()
        if raw:
            return raw
    agent_models = getattr(parent_config, "agent_models", None) or {}
    if agent_type in agent_models:
        return agent_type
    return ""


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
    if agent_type in mcp_assigns:
        cfg.mcp_servers = list(mcp_assigns[agent_type] or [])
        cfg.mcp_inherit = False
    elif not cfg.mcp_servers:
        cfg.mcp_inherit = True

    slot = spawn_model_slot(agent_type, parent_config, profile)
    # Empty / main → inherit parent model (cfg.model stays unset)
    if slot:
        try:
            resolved = resolve_subagent_model_id(parent_config, profile, slot)
            if resolved:
                cfg.model = resolved
                logger.info(
                    "Sub-agent %s model_slot %r → model %r",
                    agent_type,
                    slot,
                    resolved,
                )
        except Exception:
            logger.exception(
                "Failed to resolve model_slot %r for sub-agent %s",
                slot,
                agent_type,
            )

    tools = list(cfg.tools or [])
    for extra in ("ask_user", "tool_search", "session_search"):
        if extra not in tools:
            tools.append(extra)
    if "terminal" in tools or "run_terminal_command" in tools:
        for bg in (
            "start_background_process",
            "check_background_process",
            "stop_background_process",
            "list_background_processes",
            "restart_background_process",
        ):
            if bg not in tools:
                tools.append(bg)
    cfg.tools = _inject_external_cli_tools(agent_type, profile, tools)
    return cfg
