"""Main CLI entry point for Helix."""

import typer
from typing import Optional
from rich.traceback import install

# Install rich traceback handler
install(show_locals=True)

from cli.core import init_profile, get_current_profile, get_profile_manager
from cli.utils.rich_console import console, print_info
from cli.commands import chat, run, gateway, skills, memory, config, models

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
app.add_typer(models.app, name="models")


@app.callback()
def main(
    ctx: typer.Context,
    profile: str = typer.Option(
        "default",
        "--profile", "-p",
        help="Profile name to use",
        show_default=True
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
    config = init_profile(profile)

    # Store context
    ctx.obj = {
        "profile": profile,
        "config": config,
        "verbose": verbose
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
def gateway_command(
    ctx: typer.Context,
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
):
    """Start OpenAI-compatible API gateway.

    Launch the FastAPI server for API access to Helix.

    Example:
        helix gateway --port 8000 --reload
    """
    gateway.start_gateway(host, port, reload)


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

    if profiles:
        rows = [[p, "✓" if p == profile else ""] for p in profiles]
        print_table("Available Profiles", ["Profile", "Active"], rows)


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
        print_success(f"Profile '{profile}' cleared successfully")
    else:
        print_error(f"Profile '{profile}' data directory not found")


@app.command(name="models-legacy", hidden=True)
def models_legacy():
    """List available models (if using Ollama) - legacy command.

    Query the LLM provider for available models.
    """
    from cli.utils.rich_console import print_table, print_error
    import httpx

    try:
        response = httpx.get("http://localhost:11434/api/tags", timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            models_list = data.get("models", [])

            if models_list:
                rows = [[m["name"], m.get("size", "N/A")] for m in models_list]
                print_table("Available Models", ["Model", "Size"], rows)
            else:
                print_info("No models found")
        else:
            print_error("Failed to fetch models from Ollama")
    except Exception as e:
        print_error(f"Could not connect to Ollama: {e}")
        print_info("Make sure Ollama is running: ollama serve")


@app.command()
def version():
    """Show Helix version information."""
    from cli import __version__
    from cli.utils.rich_console import print_panel

    info = f"""[bold cyan]Helix AI Agent[/bold cyan]
Version: {__version__}
Homepage: https://github.com/yourusername/helix
License: MIT
"""
    print_panel(info, title="Version Info", border_style="cyan")


if __name__ == "__main__":
    app()
