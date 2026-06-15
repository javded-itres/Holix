"""External coding CLIs (Claude Code, OpenCode, …) launched via tmux."""

from core.external_cli.platform import ensure_launch_platform, tmux_available
from core.external_cli.registry import (
    EXTERNAL_CLI_REGISTRY,
    ExternalCliSpec,
    format_cli_id_choices,
    get_cli_spec,
    list_cli_specs,
    resolve_cli_selection,
    resolve_cli_token,
)
from core.external_cli.store import ExternalCliBinding, ExternalCliStore, LaunchedSession

__all__ = [
    "EXTERNAL_CLI_REGISTRY",
    "ExternalCliBinding",
    "ExternalCliSpec",
    "ExternalCliStore",
    "LaunchedSession",
    "ensure_launch_platform",
    "format_cli_id_choices",
    "get_cli_spec",
    "list_cli_specs",
    "resolve_cli_selection",
    "resolve_cli_token",
    "tmux_available",
]