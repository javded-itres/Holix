"""Main CLI entry point for Helix."""

import typer
from typing import Optional
from rich.traceback import install

# Install rich traceback handler
install(show_locals=True)

from cli.core import init_profile, get_current_profile, get_profile_manager
from cli.utils.rich_console import console, print_info
from cli.commands import chat, run, gateway, skills, memory, config, models, doctor, profile
from cli.commands.mcp import app as mcp_app
from cli.commands.search import app as search_app
from cli.commands.cron import app as cron_app
from cli.commands.logs import app as logs_app
from cli.commands.hub import app as hub_app
from cli.commands.install_cmd import app as install_app
from cli.commands.update_cmd import app as update_app
from cli.commands.docs import app as docs_app
from cli.commands.telegram import register_telegram_command

# Create Typer app
app = typer.Typer(
    name="helix",
    help="Helix - Self-Improving AI Agent with Memory and Skills",
    add_completion=False,
    rich_markup_mode="rich"
)

# Add command modules
app.add_typer(skills.app, name="skills")
app.add_typer(memory.app, name="memory")
app.add_typer(config.app, name="config")
app.add_typer(profile.app, name="profile")
app.add_typer(models.app, name="models")
register_telegram_command(app)
app.add_typer(gateway.app, name="gateway")
app.add_typer(doctor.app, name="doctor")
app.add_typer(mcp_app, name="mcp")
app.add_typer(search_app, name="search")
app.add_typer(cron_app, name="cron")
app.add_typer(logs_app, name="logs")
app.add_typer(hub_app, name="hub")
app.add_typer(install_app, name="install")
app.add_typer(update_app, name="update")
app.add_typer(docs_app, name="docs")


@app.callback()
def main(
    ctx: typer.Context,
    profile: str = typer.Option(
        "default",
        "--profile", "-p",
        help="Profile name to use",
        show_default=True
    ),
    profile_key: Optional[str] = typer.Option(
        None,
        "--profile-key",
        envvar="HELIX_PROFILE_KEY",
        help="Access key for a protected profile",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Enable verbose output"
    ),
):
    """Helix AI Agent CLI.

    A powerful, self-improving AI agent with memory, skills, and tool-calling capabilities.
    """
    # Initialize profile
    from core.profile_keys import ProfileKeyError

    try:
        config = init_profile(profile, profile_key=profile_key)
    except ProfileKeyError as exc:
        from cli.utils.rich_console import print_error

        print_error(str(exc))
        raise typer.Exit(1) from exc

    # Store context
    ctx.obj = {
        "profile": profile,
        "config": config,
        "verbose": verbose,
        "profile_key": profile_key,
    }

    if verbose:
        print_info(f"Using profile: {profile}")
        print_info(f"Model: {config.model}")


@app.command()
def chat_command(
    ctx: typer.Context,
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override model"),
    temperature: Optional[float] = typer.Option(None, "--temperature", "-t", help="Override temperature"),
    max_steps: Optional[int] = typer.Option(None, "--max-steps", help="Override max steps"),
):
    """Start interactive chat session.

    Launch an interactive chat interface with Helix. Supports special commands:

    - /clear - Clear conversation
    - /model <name> - Switch model
    - /profile <name> - Switch profile
    - /skills - Show skills
    - /memory <query> - Search memory
    - /exit - Exit chat
    """
    import asyncio

    profile = ctx.obj["profile"]
    config = ctx.obj["config"]

    # Apply overrides
    if model:
        config.model = model
    if temperature is not None:
        config.temperature = temperature
    if max_steps:
        config.max_steps = max_steps

    asyncio.run(chat.run_interactive_chat(profile, config))


@app.command(name="run")
def run_command(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Query to execute"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override model"),
    temperature: Optional[float] = typer.Option(None, "--temperature", "-t", help="Override temperature"),
    conversation_id: str = typer.Option("cli_oneshot", "--conversation-id", "-c", help="Conversation ID"),
):
    """Execute a single query and exit.

    Run a one-shot query without entering interactive mode.

    Example:
        helix run "Create a FastAPI endpoint for user registration"
    """
    import asyncio

    profile = ctx.obj["profile"]
    config = ctx.obj["config"]

    # Apply overrides
    if model:
        config.model = model
    if temperature is not None:
        config.temperature = temperature

    asyncio.run(run.run_single_query(query, conversation_id, config))


@app.command()
def status(ctx: typer.Context):
    """Show current profile status and information.

    Display information about the active profile, model, and statistics.
    """
    from cli.utils.rich_console import print_table, print_panel

    profile = ctx.obj["profile"]
    config = ctx.obj["config"]

    # Profile info
    info_lines = [
        f"[cyan]Profile:[/cyan] {profile}",
        f"[cyan]Model:[/cyan] {config.model}",
        f"[cyan]Base URL:[/cyan] {config.base_url}",
        f"[cyan]Temperature:[/cyan] {config.temperature}",
        f"[cyan]Max Steps:[/cyan] {config.max_steps}",
        f"[cyan]Data Directory:[/cyan] {config.data_dir}",
    ]

    print_panel("\n".join(info_lines), title="Profile Status", border_style="cyan")

    # Available profiles
    manager = get_profile_manager()
    profiles = manager.list_profiles()

    from core.profile_keys import profile_has_access_key

    if profiles:
        rows = [
            [
                p,
                "locked" if profile_has_access_key(p) else "open",
                "✓" if p == profile else "",
            ]
            for p in profiles
        ]
        print_table("Available Profiles", ["Profile", "Access", "Active"], rows)


@app.command()
def clear(
    ctx: typer.Context,
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Clear all data for current profile.

    WARNING: This will delete all memory, skills, and data for the active profile.
    """
    from cli.utils.rich_console import print_warning, print_success, print_error
    import shutil

    profile = ctx.obj["profile"]

    if profile == "default" and not confirm:
        print_warning("You are about to clear the default profile!")

    if not confirm:
        response = typer.confirm(f"Are you sure you want to clear profile '{profile}'?")
        if not response:
            print_info("Cancelled")
            return

    manager = get_profile_manager()
    profile_dir = manager.get_profile_dir(profile)
    data_dir = profile_dir / "data"

    if data_dir.exists():
        shutil.rmtree(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "memory").mkdir(parents=True, exist_ok=True)
        (data_dir / "skills").mkdir(parents=True, exist_ok=True)
        (data_dir / "security").mkdir(parents=True, exist_ok=True)
        (data_dir / "files").mkdir(parents=True, exist_ok=True)
        print_success(f"Profile '{profile}' cleared successfully")
    else:
        print_error(f"Profile '{profile}' data directory not found")


@app.command()
def version():
    """Show Helix version information."""
    from cli import __version__
    from cli.utils.rich_console import print_panel

    info = f"""[bold cyan]Helix AI Agent[/bold cyan]
Version: {__version__}
Homepage: https://github.com/javded-itres/HelixAgent
License: MIT
"""
    print_panel(info, title="Version Info", border_style="cyan")


@app.command()
def tui(
    ctx: typer.Context,
    profile: str = typer.Option(
        "default",
        "--profile", "-p",
        help="Profile to use",
        show_default=True
    ),
    web: bool = typer.Option(
        False,
        "--web",
        help="Serve TUI in the browser (requires: uv sync --extra tui-web)",
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Bind address for --web",
    ),
    port: int = typer.Option(
        8787,
        "--port",
        help="Port for --web",
    ),
    public_url: Optional[str] = typer.Option(
        None,
        "--public-url",
        help="Public URL when behind a reverse proxy (--web)",
    ),
    token: Optional[str] = typer.Option(
        None,
        "--token",
        envvar="HELIX_TUI_WEB_TOKEN",
        help="Shared secret for browser access (--web). Required for LAN/production.",
    ),
    allow_lan: bool = typer.Option(
        False,
        "--allow-lan",
        help="Allow binding to 0.0.0.0 (requires --token; exposes full agent on your network)",
    ),
    generate_token: bool = typer.Option(
        True,
        "--generate-token/--no-generate-token",
        help="On 127.0.0.1 only: create an ephemeral token if --token is omitted",
    ),
):
    """Launch the full-screen Textual TUI (terminal or browser with --web).

    Starts a modern terminal interface with live event updates,
    tool visibility, and better multitasking feel.
    """
    if web:
        from cli.tui.web_serve import run_tui_web
        from cli.tui.web_security import WebTuiSecurityError
        from cli.utils.rich_console import print_error, print_info

        try:
            run_tui_web(
                profile,
                host=host,
                port=port,
                public_url=public_url,
                token=token,
                allow_lan=allow_lan,
                generate_token=generate_token,
            )
        except WebTuiSecurityError as e:
            print_error(str(e))
            raise typer.Exit(1) from e
        except RuntimeError as e:
            print_error(str(e))
            raise typer.Exit(1) from e
        except KeyboardInterrupt:
            print_info("Web TUI stopped")
        return

    from cli.tui.app import run_tui
    run_tui(profile=profile)


def main() -> None:
    """Console entry point (``pip install`` → ``helix`` on PATH)."""
    from core.logging.setup import configure_helix_logging
    from core.platform_compat import ensure_multiprocessing_support

    ensure_multiprocessing_support()
    configure_helix_logging()
    app()


if __name__ == "__main__":
    main()
