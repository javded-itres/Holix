"""Profile isolation commands: env, workspace jail."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import typer

from cli.core import get_current_config, get_profile_manager
from cli.utils.rich_console import print_error, print_info, print_success, print_warning

app = typer.Typer(help="Manage profile isolation (env, workspace jail)")
jail_app = typer.Typer(help="Restrict agent file/terminal access to one directory")
app.add_typer(jail_app, name="jail")


def _profile(ctx: typer.Context) -> str:
    return ctx.obj["profile"]


@app.command("env")
def profile_env(
    ctx: typer.Context,
    edit: bool = typer.Option(False, "--edit", "-e", help="Open profile .env in editor"),
) -> None:
    """Show or edit the active profile's ``.env`` file."""
    from core.env_loader import ensure_profile_env_template, profile_env_path

    profile = _profile(ctx)
    path = ensure_profile_env_template(profile)

    if edit:
        editor = os.environ.get("EDITOR", "nano")
        print_info(f"Opening {path} in {editor}…")
        try:
            subprocess.run([editor, str(path)], check=False)
            print_success("Profile env updated")
            print_info("Restart gateway/Telegram or re-run CLI for changes to apply")
        except OSError as e:
            print_error(f"Failed to open editor: {e}")
            raise typer.Exit(1) from e
        return

    print_info(f"Profile: {profile}")
    print_info(f"Env file: {path}")
    if path.is_file():
        print_info(path.read_text(encoding="utf-8"))
    else:
        print_warning("Env file is empty or missing")


@jail_app.command("enable")
def jail_enable(
    ctx: typer.Context,
    path: str = typer.Argument(..., help="Directory the agent must stay inside"),
) -> None:
    """Enable workspace jail for the active profile."""
    profile = _profile(ctx)
    manager = get_profile_manager()
    config = manager.load_profile(profile)

    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        print_error(f"Directory does not exist: {root}")
        raise typer.Exit(1)

    config.workspace_jail_enabled = True
    config.workspace_root = str(root)
    manager.save_profile(profile, config)
    print_success(f"Workspace jail enabled for profile '{profile}'")
    print_info(f"Root: {root}")
    print_info("File and terminal tools are restricted to this directory tree.")


@jail_app.command("disable")
def jail_disable(ctx: typer.Context) -> None:
    """Disable workspace jail for the active profile."""
    profile = _profile(ctx)
    manager = get_profile_manager()
    config = manager.load_profile(profile)

    config.workspace_jail_enabled = False
    config.workspace_root = None
    manager.save_profile(profile, config)
    print_success(f"Workspace jail disabled for profile '{profile}'")


@jail_app.command("status")
def jail_status(ctx: typer.Context) -> None:
    """Show workspace jail settings for the active profile."""
    from cli.utils.rich_console import print_panel

    config = get_current_config()
    if config.workspace_jail_enabled and config.workspace_root:
        body = (
            f"[green]Enabled[/green]\n"
            f"[cyan]Root:[/cyan] {config.workspace_root}\n\n"
            "The agent cannot read/write/run commands outside this directory."
        )
        border = "green"
    else:
        body = (
            "[yellow]Disabled[/yellow]\n\n"
            "Enable with: [cyan]helix profile jail enable /path/to/dir[/cyan]"
        )
        border = "yellow"

    print_panel(body, title=f"Workspace jail — {config.profile_name}", border_style=border)