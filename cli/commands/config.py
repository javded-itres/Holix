"""Configuration management commands."""

import os
import subprocess

import typer

from cli.core import get_profile_manager
from cli.utils.rich_console import print_error, print_info, print_success

app = typer.Typer(help="Manage Helix configuration")


@app.command("edit")
def edit_config(ctx: typer.Context):
    """Open profile configuration in editor."""
    profile = ctx.obj["profile"]
    manager = get_profile_manager()

    config_file = manager.get_profile_dir(profile) / "config.yaml"

    if not config_file.exists():
        print_error(f"Config file not found: {config_file}")
        return

    # Get editor from environment or use default
    editor = os.environ.get("EDITOR", "nano")

    print_info(f"Opening {config_file} in {editor}...")

    try:
        subprocess.run([editor, str(config_file)])
        print_success("Configuration updated")
        print_info("Restart Helix for changes to take effect")
    except Exception as e:
        print_error(f"Failed to open editor: {e}")


@app.command("show")
def show_config(ctx: typer.Context):
    """Show current configuration."""
    import yaml

    from cli.utils.rich_console import print_panel

    config = ctx.obj["config"]

    config_yaml = yaml.dump(config.model_dump(), default_flow_style=False)
    print_panel(config_yaml, title=f"Configuration: {config.profile_name}", border_style="cyan")


@app.command("set")
def set_config(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Configuration key"),
    value: str = typer.Argument(..., help="Configuration value")
):
    """Set a configuration value."""
    profile = ctx.obj["profile"]
    config = ctx.obj["config"]
    manager = get_profile_manager()

    # Update config
    if hasattr(config, key):
        # Try to convert value to appropriate type
        current_val = getattr(config, key)
        if isinstance(current_val, bool):
            value = value.lower() in ('true', '1', 'yes')
        elif isinstance(current_val, int):
            value = int(value)
        elif isinstance(current_val, float):
            value = float(value)

        setattr(config, key, value)
        manager.save_profile(profile, config)
        print_success(f"Set {key} = {value}")
    else:
        print_error(f"Unknown configuration key: {key}")
