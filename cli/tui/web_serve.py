"""Serve Holix Textual TUI in the browser via textual-serve."""

from __future__ import annotations

import shlex
import sys

from cli.tui.web_security import (
    WebTuiSecurityPolicy,
    build_web_tui_policy,
    is_loopback_host,
    is_wildcard_bind,
    public_url_with_token,
)


def run_tui_web(
    profile: str = "default",
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    public_url: str | None = None,
    token: str | None = None,
    allow_lan: bool = False,
    generate_token: bool = True,
) -> WebTuiSecurityPolicy:
    """Start a local web server; each browser tab gets a Holix TUI session."""
    try:
        from textual_serve.server import Server  # noqa: F401 — import check
    except ImportError as e:
        raise RuntimeError(
            "Web TUI requires textual-serve. Install with: pip install 'Holix[tui-web]'"
        ) from e

    from config import settings

    policy = build_web_tui_policy(
        host=host,
        cli_token=token,
        allow_lan=allow_lan,
        generate_token=generate_token,
        is_production=settings.is_production,
    )

    from cli.tui.web_server import HolixWebTuiServer

    cmd = shlex.join([sys.executable, "-m", "cli.tui.web_entry", "--profile", profile])
    server = HolixWebTuiServer(
        cmd,
        host=policy.host,
        port=port,
        title=f"Holix ({profile})",
        public_url=public_url,
        web_token=policy.token,
    )
    _print_web_tui_banner(server, policy, profile=profile)
    server.serve()
    return policy


def _print_web_tui_banner(
    server: object, policy: WebTuiSecurityPolicy, *, profile: str
) -> None:
    from rich.console import Console

    public = getattr(server, "public_url", "http://127.0.0.1:8787")
    url = public_url_with_token(public, policy.token)
    console = Console()
    console.print(f"[bold cyan]Holix Web TUI[/bold cyan] — profile [bold]{profile}[/bold]")
    console.print(f"  URL: [link={url}]{url}[/link]")
    if policy.token_generated:
        console.print("  [yellow]Ephemeral token generated for this session.[/yellow]")
    if is_wildcard_bind(policy.host):
        console.print(
            "  [bold red]LAN bind:[/bold red] anyone on your network with this URL "
            "gets full agent access (terminal, files, MCP)."
        )
    elif not is_loopback_host(policy.host):
        console.print(
            "  [yellow]Non-loopback bind:[/yellow] use a firewall and rotate the token."
        )
    elif not policy.is_production:
        console.print(
            "  [dim]Loopback only; other local users/processes need the token.[/dim]"
        )
    console.print("  [dim]Press Ctrl+C to stop.[/dim]\n")