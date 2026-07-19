"""Holix extension discovery and registration."""

from core.extensions.agent_base import (
    AgentExtension,
    AgentExtensionBase,
    AgentExtensionContext,
    SlashCommandSpec,
)
from core.extensions.agent_registry import (
    ENTRYPOINT_GROUP as AGENT_ENTRYPOINT_GROUP,
)
from core.extensions.agent_registry import (
    agent_extension_settings,
    agent_prompt_fragment,
    agent_slash_commands,
    discover_agent_extensions,
    register_agent_extensions,
    reload_agent_extensions,
)
from core.extensions.base import (
    ALL_CAPABILITIES,
    CAPABILITY_AGENT,
    CAPABILITY_CLI,
    CAPABILITY_HTTP,
    CAPABILITY_SIDECAR,
    ExtensionBase,
    ExtensionContext,
    ExtensionInfo,
    HolixExtension,
)
from core.extensions.control import (
    disable_extension,
    enable_extension,
    is_extension_blocked,
    load_control,
    quarantine_extension,
)
from core.extensions.middleware import LLMMiddleware, LLMRequestContext, MiddlewareChain
from core.extensions.registry import (
    ENTRYPOINT_GROUP,
    discover_extensions,
    get_extension,
    list_extension_info,
    load_extension_module,
    mount_gateway_extensions,
    register_cli_extensions,
    shutdown_extensions,
    startup_extensions,
)
from core.extensions.settings import (
    load_extension_settings,
    save_extension_settings,
)

__all__ = [
    "AGENT_ENTRYPOINT_GROUP",
    "ALL_CAPABILITIES",
    "CAPABILITY_AGENT",
    "CAPABILITY_CLI",
    "CAPABILITY_HTTP",
    "CAPABILITY_SIDECAR",
    "ENTRYPOINT_GROUP",
    "AgentExtension",
    "AgentExtensionBase",
    "AgentExtensionContext",
    "ExtensionBase",
    "ExtensionContext",
    "ExtensionInfo",
    "HolixExtension",
    "LLMMiddleware",
    "LLMRequestContext",
    "MiddlewareChain",
    "SlashCommandSpec",
    "agent_extension_settings",
    "agent_prompt_fragment",
    "agent_slash_commands",
    "discover_agent_extensions",
    "discover_extensions",
    "disable_extension",
    "enable_extension",
    "get_extension",
    "is_extension_blocked",
    "list_extension_info",
    "load_control",
    "load_extension_module",
    "load_extension_settings",
    "mount_gateway_extensions",
    "quarantine_extension",
    "register_agent_extensions",
    "register_cli_extensions",
    "reload_agent_extensions",
    "save_extension_settings",
    "shutdown_extensions",
    "startup_extensions",
]
