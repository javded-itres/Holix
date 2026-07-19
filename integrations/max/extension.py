"""MAX messenger integration as a Holix extension."""

from __future__ import annotations

from typing import Any

from core.extensions.base import CAPABILITY_CLI, CAPABILITY_HTTP, ExtensionBase


class MaxExtension(ExtensionBase):
    name = "max"
    version = "0.1.0"
    requires_holix = ">=0.1.21"
    description = "MAX messenger bot: setup, run, and gateway management API"
    capabilities = frozenset({CAPABILITY_CLI, CAPABILITY_HTTP})
    permissions = frozenset({"network", "gateway", "tools"})

    def register_cli(self, root: Any) -> None:
        from cli.commands.max import register_max_command

        register_max_command(root)

    def mount_gateway(self, app: Any) -> None:
        from integrations.max.gateway_routes import register_max_routes

        register_max_routes(app)


def get_extension() -> MaxExtension:
    return MaxExtension()