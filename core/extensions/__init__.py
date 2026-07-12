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
    agent_prompt_fragment,
    agent_slash_commands,
    discover_agent_extensions,
    register_agent_extensions,
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
    "SlashCommandSpec",
    "agent_prompt_fragment",
    "agent_slash_commands",
    "discover_agent_extensions",
    "discover_extensions",
    "get_extension",
    "list_extension_info",
    "load_extension_module",
    "mount_gateway_extensions",
    "register_agent_extensions",
    "register_cli_extensions",
    "shutdown_extensions",
    "startup_extensions",
]