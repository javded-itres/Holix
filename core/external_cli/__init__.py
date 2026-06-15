"""External coding CLIs (Claude Code, OpenCode, …) launched via tmux."""

from core.external_cli.platform import ensure_launch_platform, tmux_available
from core.external_cli.registry import (
    EXTERNAL_CLI_REGISTRY,
    ExternalCliSpec,
    get_cli_spec,
    list_cli_specs,
)
from core.external_cli.store import ExternalCliBinding, ExternalCliStore, LaunchedSession

__all__ = [
    "EXTERNAL_CLI_REGISTRY",
    "ExternalCliBinding",
    "ExternalCliSpec",
    "ExternalCliStore",
    "LaunchedSession",
    "ensure_launch_platform",
    "get_cli_spec",
    "list_cli_specs",
    "tmux_available",
]