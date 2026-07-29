"""API Gateway commands: start, stop, status, reload."""

from __future__ import annotations

import os

import typer

from cli.services.gateway_daemon import (
    gateway_status,
    reload_gateway_daemon,
    restart_gateway_daemon,
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
    """Reload profile configuration (agent, companions, docs) without stopping gateway."""
    reload_gateway_daemon(_profile(ctx))


@app.command("restart")
def gateway_restart(ctx: typer.Context) -> None:
    """Fully restart gateway and all companion processes (stop → start)."""
    restart_gateway_daemon(_profile(ctx))


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

# ── API keys (gateway auth) ──────────────────────────────────────────────

keys_app = typer.Typer(help="Manage gateway API keys (auth for /v1)", no_args_is_help=True)
app.add_typer(keys_app, name="keys")


def _keys_manager():
    from core.security.auth import APIKeyManager

    return APIKeyManager()


@keys_app.command("create")
def keys_create(
    name: str = typer.Option(..., "--name", "-n", help="Key label"),
    permissions: str = typer.Option(
        "read,write,execute",
        "--permissions",
        "-p",
        help="Comma list: read,write,execute,admin",
    ),
    rate_limit: int = typer.Option(100, "--rate-limit", "-r", help="Requests per minute"),
    profiles: str = typer.Option(
        "",
        "--profiles",
        help="Comma list of allowed profiles (empty = all profiles)",
    ),
):
    """Create a gateway API key. Print once — not stored in plaintext."""
    import asyncio

    from cli.utils.rich_console import print_info, print_success, print_warning

    async def _run() -> str:
        mgr = _keys_manager()
        await mgr.initialize_db()
        allowed = profiles.strip() or None
        return await mgr.create_api_key(
            name=name,
            permissions=permissions,
            rate_limit=rate_limit,
            allowed_profiles=allowed,
        )

    try:
        key = asyncio.run(_run())
    except Exception as e:
        print_error(f"Failed to create key: {e}")
        raise typer.Exit(1) from e
    print_success(f"Created API key '{name}'")
    print_info(f"permissions: {permissions}")
    print_info(f"rate_limit:  {rate_limit}")
    print_info(f"profiles:    {profiles.strip() or '(all)'}")
    print_warning("Save this secret now — it will not be shown again:")
    print(key)


@keys_app.command("list")
def keys_list():
    """List gateway API keys (metadata only)."""
    import asyncio

    from rich.console import Console
    from rich.table import Table

    from cli.utils.rich_console import print_info

    async def _run():
        mgr = _keys_manager()
        await mgr.initialize_db()
        return await mgr.list_api_keys()

    try:
        rows = asyncio.run(_run())
    except Exception as e:
        print_error(f"Failed to list keys: {e}")
        raise typer.Exit(1) from e

    table = Table(title="Gateway API keys")
    table.add_column("id")
    table.add_column("name")
    table.add_column("permissions")
    table.add_column("profiles")
    table.add_column("active")
    table.add_column("rate")
    for row in rows:
        table.add_row(
            str(row.get("id")),
            str(row.get("name")),
            str(row.get("permissions")),
            str(row.get("allowed_profiles") or "*"),
            "yes" if row.get("is_active") else "no",
            str(row.get("rate_limit")),
        )
    Console().print(table)
    print_info(f"{len(rows)} key(s)")


@keys_app.command("revoke")
def keys_revoke(
    api_key: str = typer.Argument(..., help="Full API key secret (hx_…)"),
):
    """Revoke a gateway API key by its secret value."""
    import asyncio

    from cli.utils.rich_console import print_success

    async def _run() -> bool:
        mgr = _keys_manager()
        await mgr.initialize_db()
        return await mgr.revoke_api_key(api_key)

    try:
        ok = asyncio.run(_run())
    except Exception as e:
        print_error(f"Failed to revoke: {e}")
        raise typer.Exit(1) from e
    if not ok:
        print_error("Key not found or already inactive")
        raise typer.Exit(1)
    print_success("API key revoked")
