"""Holix Studio — desktop and web IDE client."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="studio",
    help="Holix Studio (chat + workspace IDE) — local serve and Electron launcher",
    no_args_is_help=True,
)


@app.command("serve")
def studio_serve(
    profile: str = typer.Option(
        "default",
        "--profile",
        "-p",
        help="Holix profile",
        show_default=True,
    ),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address"),
    port: int = typer.Option(8788, "--port", help="HTTP port"),
    token: str | None = typer.Option(
        None,
        "--token",
        envvar="HOLIX_STUDIO_TOKEN",
        help="Shared secret for browser/WebSocket access",
    ),
    allow_lan: bool = typer.Option(
        False,
        "--allow-lan",
        help="Allow 0.0.0.0 bind (requires --token)",
    ),
    generate_token: bool = typer.Option(
        True,
        "--generate-token/--no-generate-token",
        help="On loopback: create ephemeral token if --token omitted",
    ),
    cwd: str | None = typer.Option(
        None,
        "--cwd",
        help="Workspace directory to show in the file tree (default: current directory)",
    ),
    open_browser: bool = typer.Option(
        False,
        "--open",
        help="Open Studio in the default browser after start",
    ),
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Run without opening a browser (for CI/smoke)",
    ),
) -> None:
    """Start Studio sidecar: static UI, files API, agent WebSocket."""
    from integrations.desktop.security import StudioSecurityError, build_studio_policy
    from integrations.desktop.serve import run_studio_server

    from cli.utils.rich_console import print_error
    from config import settings

    try:
        policy = build_studio_policy(
            host=host,
            cli_token=token,
            allow_lan=allow_lan,
            generate_token=generate_token,
            is_production=settings.is_production,
        )
    except StudioSecurityError as e:
        print_error(str(e))
        raise typer.Exit(1) from e

    from pathlib import Path

    run_studio_server(
        profile,
        policy,
        port=port,
        headless=headless,
        open_browser=open_browser,
        serve_cwd=Path(cwd).expanduser().resolve() if cwd else None,
    )


@app.command("open")
def studio_open(
    profile: str = typer.Option("default", "--profile", "-p", show_default=True),
) -> None:
    """Launch Studio (starts serve and opens browser). Alias for serve --open."""
    studio_serve(
        profile=profile,
        host="127.0.0.1",
        port=8788,
        token=None,
        allow_lan=False,
        generate_token=True,
        open_browser=True,
        headless=False,
    )