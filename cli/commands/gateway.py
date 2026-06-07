"""API Gateway commands: start, stop, status, reload."""

from __future__ import annotations

import typer

from config import settings
from cli.services.gateway_daemon import (
    gateway_status,
    reload_gateway_daemon,
    start_gateway_daemon,
    stop_gateway_daemon,
)
from cli.utils.rich_console import print_error

app = typer.Typer(
    help="Manage Helix API gateway and companion services (Telegram, …)",
    no_args_is_help=True,
)


def _profile(ctx: typer.Context) -> str:
    return ctx.obj["profile"]


@app.command("start")
def gateway_start(
    ctx: typer.Context,
    host: str = typer.Option(settings.gateway_host, "--host", help="Host to bind"),
    port: int = typer.Option(settings.gateway_port, "--port", "-p", help="Port to bind"),
    reload: bool = typer.Option(False, "--reload", help="Enable code auto-reload (dev)"),
    foreground: bool = typer.Option(
        False,
        "--foreground",
        "-f",
        help="Run in foreground (do not detach)",
    ),
    with_docs: bool = typer.Option(
        settings.gateway_with_docs,
        "--with-docs",
        help="Also serve the documentation site (or set HELIX_GATEWAY_WITH_DOCS=1)",
    ),
    docs_host: str = typer.Option(settings.docs_host, "--docs-host", help="Docs bind address"),
    docs_port: int = typer.Option(settings.docs_port, "--docs-port", help="Docs HTTP port"),
):
    """Start gateway and companion services in the background.

    Example:
        helix gateway start
        helix gateway start --port 8000 --profile work
        helix gateway start --with-docs --docs-port 8080
        helix gateway start -f   # foreground, blocks terminal
    """
    try:
        start_gateway_daemon(
            host,
            port,
            reload=reload,
            profile=_profile(ctx),
            foreground=foreground,
            with_docs=with_docs,
            docs_host=docs_host,
            docs_port=docs_port,
        )
    except SystemExit:
        raise
    except Exception as e:
        print_error(f"Failed to start gateway: {e}")
        raise typer.Exit(1) from e


@app.command("stop")
def gateway_stop() -> None:
    """Stop background gateway and companion services."""
    stop_gateway_daemon()


@app.command("status")
def gateway_status_cmd() -> None:
    """Show gateway process and health status."""
    gateway_status()


@app.command("reload")
def gateway_reload() -> None:
    """Restart gateway with the same host, port, and profile."""
    reload_gateway_daemon()