"""Main CLI entry point for Holix."""

from __future__ import annotations

import sys

import typer
from rich.traceback import install

# Install rich traceback handler
install(show_locals=True)

from core.profile_keys import ProfileNotFoundError

from cli.core import get_profile_manager, init_profile, resolve_active_profile_name
from cli.utils.rich_console import print_info

# Create Typer app
app = typer.Typer(
    name="holix",
    help="Holix - Self-Improving AI Agent with Memory and Skills",
    add_completion=False,
    rich_markup_mode="rich"
)

_BASE_COMMANDS_REGISTERED = False
_HEAVY_COMMANDS_REGISTERED = False

# Commands that pull chromadb/numpy via HolixAgent or SkillsManager.
_HEAVY_ROOT_COMMANDS = frozenset({"chat", "run", "tui", "skills", "memory"})


def _needs_heavy_commands(argv: list[str]) -> bool:
    """Return True when argv invokes agent/memory-heavy CLI modules."""
    if not argv or argv[0].startswith("-"):
        return False
    root = argv[0]
    if root in _HEAVY_ROOT_COMMANDS:
        return True
    # ``holix --profile X chat`` / ``holix -p X run ...``
    for index, token in enumerate(argv):
        if token in {"--profile", "-p"} and index + 1 < len(argv):
            continue
        if token in _HEAVY_ROOT_COMMANDS:
            return True
    return False


def _register_base_commands() -> None:
    """Register lightweight subcommands (safe on old CPUs / before chromadb)."""
    global _BASE_COMMANDS_REGISTERED
    if _BASE_COMMANDS_REGISTERED:
        return

    from cli.commands import config, doctor, gateway, models, profile
    from cli.commands.bootstrap import app as bootstrap_app
    from cli.commands.cron import app as cron_app
    from cli.commands.docs import app as docs_app
    from cli.commands.hub import app as hub_app
    from cli.commands.install_cmd import app as install_app
    from cli.commands.logs import app as logs_app
    from cli.commands.max import register_max_command
    from cli.commands.mcp import app as mcp_app
    from cli.commands.search import app as search_app
    from cli.commands.telegram import register_telegram_command
    from cli.commands.update_cmd import app as update_app

    app.add_typer(config.app, name="config")
    app.add_typer(profile.app, name="profile")
    app.add_typer(models.app, name="models")
    register_telegram_command(app)
    register_max_command(app)
    app.add_typer(gateway.app, name="gateway")
    app.add_typer(doctor.app, name="doctor")
    app.add_typer(mcp_app, name="mcp")
    app.add_typer(search_app, name="search")
    app.add_typer(cron_app, name="cron")
    app.add_typer(logs_app, name="logs")
    app.add_typer(hub_app, name="hub")
    app.add_typer(install_app, name="install")
    app.add_typer(bootstrap_app, name="bootstrap")
    app.add_typer(update_app, name="update")
    app.add_typer(docs_app, name="docs")
    _BASE_COMMANDS_REGISTERED = True


def _register_heavy_commands() -> None:
    """Register subcommands that import chromadb (agent, skills, memory)."""
    global _HEAVY_COMMANDS_REGISTERED
    if _HEAVY_COMMANDS_REGISTERED:
        return

    from cli.commands import memory, skills

    app.add_typer(skills.app, name="skills")
    app.add_typer(memory.app, name="memory")
    _HEAVY_COMMANDS_REGISTERED = True


def _register_commands(argv: list[str] | None = None) -> None:
    _register_base_commands()
    if _needs_heavy_commands(argv or sys.argv[1:]):
        _register_heavy_commands()


@app.callback()
def _app_callback(
    ctx: typer.Context,
    profile: str | None = typer.Option(
        None,
        "--profile", "-p",
        help="Profile name (required in production; implicit default is dev-only)",
    ),
    profile_key: str | None = typer.Option(
        None,
        "--profile-key",
        envvar="HOLIX_PROFILE_KEY",
        help="Access key for a protected profile",
    ),
    unlock_key: str | None = typer.Option(
        None,
        "--unlock-key",
        envvar="HOLIX_UNLOCK_KEY",
        help="Encryption unlock key for an encrypted profile",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Enable verbose output"
    ),
):
    """Holix AI Agent CLI.

    A powerful, self-improving AI agent with memory, skills, and tool-calling capabilities.
    """
    # Initialize profile
    from core.crypto.profile_crypto import ProfileCryptoError
    from core.profile_keys import ProfileKeyError

    from cli.utils.rich_console import print_error

    try:
        resolved_profile = resolve_active_profile_name(profile)
        config = init_profile(
            resolved_profile,
            profile_key=profile_key,
            unlock_key=unlock_key,
        )
    except ProfileNotFoundError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc
    except ProfileKeyError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc
    except ProfileCryptoError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc

    # Store context
    ctx.obj = {
        "profile": resolved_profile,
        "config": config,
        "verbose": verbose,
        "profile_key": profile_key,
        "unlock_key": unlock_key,
    }

    if verbose:
        print_info(f"Using profile: {resolved_profile}")
        print_info(f"Model: {config.model}")


@app.command()
def chat_command(
    ctx: typer.Context,
    model: str | None = typer.Option(None, "--model", "-m", help="Override model"),
    temperature: float | None = typer.Option(None, "--temperature", "-t", help="Override temperature"),
    max_steps: int | None = typer.Option(None, "--max-steps", help="Override max steps"),
):
    """Start interactive chat session.

    Launch an interactive chat interface with Holix. Supports special commands:

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

    from cli.commands import chat

    asyncio.run(chat.run_interactive_chat(profile, config))


@app.command(name="run")
def run_command(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Query to execute"),
    model: str | None = typer.Option(None, "--model", "-m", help="Override model"),
    temperature: float | None = typer.Option(None, "--temperature", "-t", help="Override temperature"),
    conversation_id: str = typer.Option("cli_oneshot", "--conversation-id", "-c", help="Conversation ID"),
):
    """Execute a single query and exit.

    Run a one-shot query without entering interactive mode.

    Example:
        holix run "Create a FastAPI endpoint for user registration"
    """
    import asyncio

    ctx.obj["profile"]
    config = ctx.obj["config"]

    # Apply overrides
    if model:
        config.model = model
    if temperature is not None:
        config.temperature = temperature

    from cli.commands import run

    asyncio.run(run.run_single_query(query, conversation_id, config))


@app.command()
def status(ctx: typer.Context):
    """Show current profile status and information.

    Display information about the active profile, model, and statistics.
    """
    from cli.utils.rich_console import print_panel, print_table

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
    import shutil

    from cli.utils.rich_console import print_error, print_success, print_warning

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
    """Show Holix version information."""
    from cli import __version__
    from cli.utils.rich_console import print_panel

    info = f"""[bold cyan]Holix AI Agent[/bold cyan]
Version: {__version__}
Homepage: https://github.com/javded-itres/Holix
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
    public_url: str | None = typer.Option(
        None,
        "--public-url",
        help="Public URL when behind a reverse proxy (--web)",
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        envvar="HOLIX_TUI_WEB_TOKEN",
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
        from cli.tui.web_security import WebTuiSecurityError
        from cli.tui.web_serve import run_tui_web
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


# Register lightweight subcommands at import so ``CliRunner(app)`` in tests works.
_register_base_commands()


def main() -> None:
    """Console entry point (``pip install`` → ``holix`` on PATH)."""
    from core.logging.setup import configure_holix_logging
    from core.platform_compat import ensure_multiprocessing_support

    ensure_multiprocessing_support()
    configure_holix_logging()
    if _needs_heavy_commands(sys.argv[1:]):
        _register_heavy_commands()
    app()


if __name__ == "__main__":
    main()
