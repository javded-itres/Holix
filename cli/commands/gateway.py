"""API Gateway commands: start, stop, status, reload."""

from __future__ import annotations

import os

import typer

from cli.services.gateway_daemon import (
    gateway_status,
    reload_gateway_daemon,
    start_gateway_daemon,
    stop_gateway_daemon,
)
from cli.utils.rich_console import print_error
from config import settings

app = typer.Typer(
    help="Manage Holix API gateway and companion services (Telegram, …)",
    no_args_is_help=True,
)


def _profile(ctx: typer.Context) -> str:
    return ctx.obj["profile"]


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@app.command("start")
def gateway_start(
    ctx: typer.Context,
    host: str = typer.Option(None, "--host", help="Host to bind"),
    port: int = typer.Option(None, "--port", "-p", help="Port to bind"),
    reload: bool = typer.Option(False, "--reload", help="Enable code auto-reload (dev)"),
    foreground: bool = typer.Option(
        False,
        "--foreground",
        "-f",
        help="Run in foreground (do not detach)",
    ),
    with_docs: bool = typer.Option(
        False,
        "--with-docs",
        help="Also serve the documentation site (or set HOLIX_GATEWAY_WITH_DOCS=1)",
    ),
    docs_host: str = typer.Option(None, "--docs-host", help="Docs bind address"),
    docs_port: int = typer.Option(None, "--docs-port", help="Docs HTTP port"),
):
    """Start gateway and companion services in the background.

    Example:
        holix gateway start
        holix gateway start --port 8000 --profile work
        holix gateway start --with-docs --docs-port 8080
        holix gateway start -f   # foreground, blocks terminal
    """
    try:
        resolved_host = host or os.getenv("HOLIX_GATEWAY_HOST", settings.gateway_host)
        resolved_port = port if port is not None else _env_int(
            "HOLIX_GATEWAY_PORT", settings.gateway_port
        )
        resolved_with_docs = with_docs or _env_bool("HOLIX_GATEWAY_WITH_DOCS") or _env_bool(
            "HOLIX_GATEWAY_DOCS"
        )
        resolved_docs_host = docs_host or os.getenv("HOLIX_DOCS_HOST", settings.docs_host)
        resolved_docs_port = (
            docs_port
            if docs_port is not None
            else _env_int("HOLIX_DOCS_PORT", settings.docs_port)
        )
        start_gateway_daemon(
            resolved_host,
            resolved_port,
            reload=reload,
            profile=_profile(ctx),
            foreground=foreground,
            with_docs=resolved_with_docs,
            docs_host=resolved_docs_host,
            docs_port=resolved_docs_port,
        )
    except SystemExit:
        raise
    except Exception as e:
        print_error(f"Failed to start gateway: {e}")
        raise typer.Exit(1) from e


@app.command("stop")
def gateway_stop(ctx: typer.Context) -> None:
    """Stop background gateway and companion services for the active profile."""
    stop_gateway_daemon(_profile(ctx))


@app.command("status")
def gateway_status_cmd(ctx: typer.Context) -> None:
    """Show gateway process and health status for the active profile."""
    gateway_status(_profile(ctx))


@app.command("reload")
def gateway_reload(ctx: typer.Context) -> None:
    """Restart gateway with the same host, port, and profile."""
    reload_gateway_daemon(_profile(ctx))


@app.command("show")
def gateway_show(ctx: typer.Context) -> None:
    """Show effective gateway settings for the active profile."""
    from cli.commands.gateway_configure import show_gateway_config

    show_gateway_config(_profile(ctx))


@app.command("configure")
def gateway_configure(
    ctx: typer.Context,
    start: bool = typer.Option(
        False,
        "--start",
        help="Start gateway after saving settings",
    ),
) -> None:
    """Interactively configure gateway host, port, auth, and docs companion.

    Example:
        holix gateway configure
        holix -p alice gateway configure --start
    """
    from cli.commands.gateway_configure import run_gateway_configure

    run_gateway_configure(profile=_profile(ctx), start_after=start)