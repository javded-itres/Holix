"""Profile isolation commands: env, workspace jail, access keys."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import typer
from core.profile_keys import (
    profile_has_access_key,
    remove_profile_access_key,
    store_profile_access_key,
    verify_profile_access_key,
)

from cli.core import get_current_config, get_profile_manager, unlock_profile
from cli.utils.rich_console import print_error, print_info, print_success, print_warning

app = typer.Typer(help="Manage profile isolation (env, workspace jail, access keys)")
global_app = typer.Typer(help="Shared global settings inherited by profiles")
jail_app = typer.Typer(help="Restrict agent file/terminal access to one directory")
key_app = typer.Typer(help="Profile access keys (required to switch into protected profiles)")
whitelist_app = typer.Typer(help="Terminal command whitelist for the active profile")
app.add_typer(global_app, name="global")
app.add_typer(jail_app, name="jail")
app.add_typer(key_app, name="key")
app.add_typer(whitelist_app, name="whitelist")


def _profile(ctx: typer.Context) -> str:
    return ctx.obj["profile"]


@app.command("create")
def profile_create(
    name: str = typer.Argument(..., help="New profile name"),
    protect: bool = typer.Option(
        False,
        "--protect",
        help="Generate an access key (profile is open by default)",
    ),
    inherit_global: bool = typer.Option(
        True,
        "--inherit/--clean",
        help="Inherit shared global settings (default) or create a standalone profile",
    ),
) -> None:
    """Create a profile (inherits global settings by default; --clean for manual setup)."""
    from cli.utils.rich_console import print_panel

    manager = get_profile_manager()
    if manager.profile_exists(name):
        print_error(f"Profile '{name}' already exists")
        raise typer.Exit(1)

    manager.create_profile(name, with_access_key=protect, inherit_global=inherit_global)
    access_key = manager.pop_last_created_access_key()
    mode = "inherits global settings" if inherit_global else "standalone (clean)"
    print_success(f"Created profile '{name}' ({mode})")
    if inherit_global:
        from core.global_config import global_config_path, global_env_path

        print_info(f"Global config: [dim]{global_config_path()}[/dim]")
        print_info(f"Global env: [dim]{global_env_path()}[/dim]")
    if access_key:
        workspace = manager.get_profile_dir(name) / "workspace"
        print_panel(
            f"[cyan]{access_key}[/cyan]\n\n"
            "Save this key — it is shown only once.\n"
            f"Workspace jail: [dim]{workspace}[/dim]\n"
            f"Switch with: [bold]helix -p {name} --profile-key <key>[/bold]",
            title="Profile access key",
            border_style="yellow",
        )
    else:
        print_info(f"Switch freely: [bold]helix -p {name}[/bold]")
        print_info("Protect later: [cyan]helix -p {name} profile key init[/cyan]")


@global_app.command("show")
def global_show() -> None:
    """Show shared global configuration (models, MCP, behavior)."""
    import yaml
    from core.global_config import global_config_path, global_env_path, load_global_config_resolved

    from cli.utils.rich_console import print_panel

    data = load_global_config_resolved()
    body = yaml.dump(data, default_flow_style=False, allow_unicode=True)
    print_panel(
        body,
        title="Global configuration",
        subtitle=f"{global_config_path()}\nEnv: {global_env_path()}",
        border_style="cyan",
    )


@global_app.command("edit")
def global_edit(
    env: bool = typer.Option(False, "--env", help="Edit global .env instead of config.yaml"),
) -> None:
    """Open global settings in $EDITOR."""
    from core.global_config import ensure_global_config, ensure_global_env_template, global_config_path

    editor = os.environ.get("EDITOR", "nano")
    if env:
        target = ensure_global_env_template()
    else:
        target = ensure_global_config()
    print_info(f"Opening {target} in {editor}...")
    try:
        subprocess.run([editor, str(target)], check=False)
        print_success("Global configuration updated")
        print_info("Profiles with --inherit pick up changes on next gateway/CLI start")
    except Exception as exc:
        print_error(f"Failed to open editor: {exc}")
        raise typer.Exit(1) from exc


@global_app.command("init")
def global_init(
    from_profile: str = typer.Option(
        "default",
        "--from-profile",
        help="Seed global config from an existing profile (empty = built-in defaults)",
    ),
) -> None:
    """Create or reset ``~/.helix/global/`` from defaults or an existing profile."""
    from core.global_config import (
        default_global_config_data,
        ensure_global_env_template,
        global_config_path,
        global_dir,
    )

    import yaml

    ensure_global_env_template()
    path = global_config_path()
    if from_profile:
        from cli.core import ProfileManager
        from core.global_config import strip_profile_only_keys

        manager = ProfileManager()
        if manager.profile_exists(from_profile):
            raw = yaml.safe_load((manager.get_profile_dir(from_profile) / "config.yaml").read_text(encoding="utf-8")) or {}
            data = strip_profile_only_keys(raw)
        else:
            print_warning(f"Profile '{from_profile}' not found — using built-in defaults")
            data = default_global_config_data()
    else:
        data = default_global_config_data()

    global_dir().mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.dump(data, handle, default_flow_style=False, allow_unicode=True)
    print_success(f"Global config written: {path}")
    print_info(f"Global env: {global_dir() / '.env'}")


@key_app.command("status")
def key_status(ctx: typer.Context) -> None:
    """Show whether the active profile requires an access key."""
    from cli.utils.rich_console import print_panel

    profile = _profile(ctx)
    if profile_has_access_key(profile):
        body = (
            "[green]Protected[/green]\n\n"
            "Switching into this profile requires its access key.\n"
            "Disable with: [cyan]helix profile key disable[/cyan]"
        )
        border = "green"
    else:
        body = (
            "[yellow]Open[/yellow]\n\n"
            "Free switching — no access key required.\n"
            "Protect with: [cyan]helix profile key init[/cyan]"
        )
        border = "yellow"
    print_panel(body, title=f"Profile access — {profile}", border_style=border)


@key_app.command("init")
def key_init(ctx: typer.Context) -> None:
    """Generate an access key for the active profile (shown once)."""
    from cli.utils.rich_console import print_panel

    profile = _profile(ctx)
    manager = get_profile_manager()
    if not manager.profile_exists(profile):
        print_error(f"Profile '{profile}' does not exist")
        raise typer.Exit(1)
    if profile_has_access_key(profile):
        print_warning(f"Profile '{profile}' already has an access key")
        raise typer.Exit(1)

    from cli.core import enable_profile_workspace_isolation

    access_key = store_profile_access_key(profile)
    workspace = enable_profile_workspace_isolation(manager, profile)
    print_success(f"Access key created for profile '{profile}'")
    print_panel(
        f"[cyan]{access_key}[/cyan]\n\n"
        "Save this key — it is shown only once.\n"
        f"Workspace jail: [dim]{workspace}[/dim]",
        title="Profile access key",
        border_style="yellow",
    )


@key_app.command("rotate")
def key_rotate(
    ctx: typer.Context,
    current_key: str = typer.Option(
        ...,
        "--current-key",
        prompt=True,
        hide_input=True,
        help="Current profile access key",
    ),
) -> None:
    """Replace the active profile access key."""
    from cli.utils.rich_console import print_panel

    profile = _profile(ctx)
    if not profile_has_access_key(profile):
        print_error("This profile has no access key yet. Use: helix profile key init")
        raise typer.Exit(1)
    if not verify_profile_access_key(profile, current_key):
        print_error("Current access key is invalid")
        raise typer.Exit(1)

    access_key = store_profile_access_key(profile)
    unlock_profile(profile, access_key)
    print_success(f"Access key rotated for profile '{profile}'")
    print_panel(
        f"[cyan]{access_key}[/cyan]\n\n"
        "Save this key — it is shown only once.",
        title="New profile access key",
        border_style="yellow",
    )


@key_app.command("disable")
def key_disable(
    ctx: typer.Context,
    current_key: str = typer.Option(
        ...,
        "--current-key",
        prompt=True,
        hide_input=True,
        help="Current profile access key",
    ),
) -> None:
    """Remove access key protection and allow free profile switching."""
    from cli import core as cli_core

    profile = _profile(ctx)
    if not profile_has_access_key(profile):
        print_warning(f"Profile '{profile}' is already open (no access key)")
        raise typer.Exit(0)
    if not verify_profile_access_key(profile, current_key):
        print_error("Current access key is invalid")
        raise typer.Exit(1)

    remove_profile_access_key(profile)
    cli_core._unlocked_profiles.discard(profile)
    print_success(f"Access key disabled for profile '{profile}'")
    print_info("Anyone can switch into this profile by name.")


@app.command("env")
def profile_env(
    ctx: typer.Context,
    edit: bool = typer.Option(False, "--edit", "-e", help="Open profile .env in editor"),
) -> None:
    """Show or edit the active profile's ``.env`` file."""
    from core.env_loader import ensure_profile_env_template

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


@whitelist_app.command("add")
def whitelist_add(
    ctx: typer.Context,
    commands: str = typer.Argument(
        ...,
        help='Comma-separated commands or prefixes, e.g. "docker, make, git push"',
    ),
) -> None:
    """Add commands to the profile terminal whitelist."""
    from core.env_loader import profile_env_path
    from core.terminal_whitelist_config import add_whitelist_commands, parse_command_list

    profile = _profile(ctx)
    parsed = parse_command_list(commands)
    if not parsed:
        print_error("No commands provided")
        raise typer.Exit(1)

    added = add_whitelist_commands(profile, commands)
    path = profile_env_path(profile)
    if added:
        print_success(f"Added to whitelist for profile '{profile}': {', '.join(added)}")
    else:
        print_info(f"All commands were already in the whitelist for profile '{profile}'")
    print_info(f"Saved in: {path}")
    print_info("Restart gateway/Telegram or re-run CLI for changes to apply")


@whitelist_app.command("list")
def whitelist_list(ctx: typer.Context) -> None:
    """List terminal whitelist settings for the active profile."""
    from core.env_loader import profile_env_path
    from core.platform_compat import IS_WINDOWS
    from core.terminal_whitelist_config import (
        builtin_whitelist_commands,
        effective_whitelist_commands,
        read_whitelist_enabled,
        read_whitelist_extra,
    )

    from cli.utils.rich_console import print_panel

    profile = _profile(ctx)
    enabled = read_whitelist_enabled(profile)
    extra = read_whitelist_extra(profile)
    builtin = builtin_whitelist_commands()
    effective = effective_whitelist_commands(profile)
    platform = "Windows" if IS_WINDOWS else "Unix"

    status = "[green]Enabled[/green]" if enabled else "[yellow]Disabled[/yellow]"
    extra_line = ", ".join(extra) if extra else "[dim]none[/dim]"
    body = (
        f"{status}\n"
        f"[cyan]Platform defaults ({platform}):[/cyan] {len(builtin)} commands\n"
        f"[cyan]Profile extras:[/cyan] {extra_line}\n"
        f"[cyan]Effective total:[/cyan] {len(effective)} commands\n\n"
        f"Env file: {profile_env_path(profile)}"
    )
    print_panel(body, title=f"Terminal whitelist — {profile}", border_style="green" if enabled else "yellow")


@whitelist_app.command("enable")
def whitelist_enable(ctx: typer.Context) -> None:
    """Enable terminal command whitelist enforcement for the active profile."""
    from core.env_loader import profile_env_path
    from core.terminal_whitelist_config import read_whitelist_enabled, set_whitelist_enabled

    profile = _profile(ctx)
    if read_whitelist_enabled(profile):
        print_info(f"Terminal whitelist is already enabled for profile '{profile}'")
        raise typer.Exit(0)

    set_whitelist_enabled(profile, True)
    print_success(f"Terminal whitelist enabled for profile '{profile}'")
    print_info(f"Saved in: {profile_env_path(profile)}")
    print_info("Restart gateway/Telegram or re-run CLI for changes to apply")