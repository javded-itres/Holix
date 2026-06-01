"""Model management commands for Helix CLI."""

import asyncio
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import box

from cli.core import get_current_config, get_profile_manager, get_current_profile
from cli.utils.rich_console import console, print_error, print_success, print_info, create_spinner
from core.models.discovery import ModelDiscovery
from core.models.provider import ProviderConfig, ModelProvider
from core.models.selector import AgentModelConfig

app = typer.Typer(help="Manage model providers and configurations")


@app.command("setup")
def setup_models(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile to configure"),
):
    """Interactive setup for model providers and routing."""
    asyncio.run(_setup_models_interactive(profile))


async def _setup_models_interactive(profile: Optional[str] = None):
    """Interactive model setup wizard."""
    if profile is None:
        profile = get_current_profile()

    config = get_current_config()
    manager = get_profile_manager()

    console.print("\n")
    console.print(Panel.fit(
        "[bold cyan]🔧 Model Provider Setup[/bold cyan]\n\n"
        "Configure OpenAI-compatible model providers (Ollama, LiteLLM, OpenAI, etc.)\n"
        "and assign models to agents and sub-agents.",
        border_style="cyan"
    ))
    console.print("\n")

    # Initialize providers dict if not exists
    if not config.providers:
        config.providers = {}

    while True:
        console.print("\n[bold]Available actions:[/bold]")
        console.print("1. Add new provider")
        console.print("2. List providers")
        console.print("3. Test provider connection")
        console.print("4. Remove provider")
        console.print("5. Configure agent models")
        console.print("6. View agent model assignments")
        console.print("7. Save and exit")
        console.print("8. Exit without saving")

        choice = Prompt.ask("\nChoose an action", choices=["1", "2", "3", "4", "5", "6", "7", "8"])

        if choice == "1":
            await _add_provider(config)
        elif choice == "2":
            _list_providers(config)
        elif choice == "3":
            await _test_provider(config)
        elif choice == "4":
            _remove_provider(config)
        elif choice == "5":
            await _configure_agent_models(config)
        elif choice == "6":
            _view_agent_models(config)
        elif choice == "7":
            manager.save_profile(profile, config)
            print_success("✓ Configuration saved successfully!")
            break
        elif choice == "8":
            if Confirm.ask("Exit without saving changes?"):
                print_info("Configuration not saved")
                break


async def _add_provider(config):
    """Add a new model provider."""
    console.print("\n[bold cyan]➕ Add New Provider[/bold cyan]\n")

    # Provider name
    name = Prompt.ask("Provider name (e.g., 'ollama', 'litellm', 'openai')")

    if name in config.providers:
        print_error(f"Provider '{name}' already exists!")
        return

    # Base URL
    base_url = Prompt.ask(
        "Base URL",
        default="http://localhost:11434/v1"
    )

    # API key
    api_key = Prompt.ask(
        "API key (press Enter for 'dummy')",
        default="dummy"
    )

    # Test connection
    console.print("\n[yellow]Testing connection...[/yellow]")

    with create_spinner() as progress:
        task = progress.add_task("Connecting to provider...", total=None)
        try:
            is_accessible = await ModelDiscovery.test_endpoint(base_url, api_key)

            if not is_accessible:
                print_error("✗ Could not connect to provider!")
                if not Confirm.ask("Add provider anyway?"):
                    return

            progress.update(task, description="Discovering models...")
            models = await ModelDiscovery.discover_models(base_url, api_key)

            if models:
                print_success(f"✓ Found {len(models)} models")

                # Display models
                table = Table(title="Available Models", box=box.ROUNDED)
                table.add_column("Model ID", style="cyan")
                table.add_column("Owned By", style="green")

                for model in models[:20]:  # Show first 20
                    table.add_row(model["id"], model.get("owned_by", "unknown"))

                console.print(table)

                if len(models) > 20:
                    console.print(f"\n[dim]... and {len(models) - 20} more models[/dim]")

                # Select default model
                model_ids = [m["id"] for m in models]
                default_model = Prompt.ask(
                    "\nDefault model to use",
                    choices=model_ids if len(model_ids) < 20 else None,
                    default=model_ids[0] if model_ids else None
                )

                # Create provider config
                provider_config = ProviderConfig(
                    name=name,
                    base_url=base_url,
                    api_key=api_key,
                    default_model=default_model,
                    available_models=model_ids
                )

                config.providers[name] = provider_config.model_dump()

                # Set as default if first provider
                if config.default_provider is None:
                    config.default_provider = name
                    print_success(f"✓ Set '{name}' as default provider")

                print_success(f"✓ Provider '{name}' added successfully!")

            else:
                print_error("✗ Could not discover models")
                if Confirm.ask("Add provider anyway?"):
                    provider_config = ProviderConfig(
                        name=name,
                        base_url=base_url,
                        api_key=api_key,
                    )
                    config.providers[name] = provider_config.model_dump()
                    print_success(f"✓ Provider '{name}' added")

        except Exception as e:
            print_error(f"✗ Error: {str(e)}")
            if Confirm.ask("Add provider anyway?"):
                provider_config = ProviderConfig(
                    name=name,
                    base_url=base_url,
                    api_key=api_key,
                )
                config.providers[name] = provider_config.model_dump()


def _list_providers(config):
    """List all configured providers."""
    if not config.providers:
        print_info("No providers configured")
        return

    console.print("\n")
    table = Table(title="Configured Providers", box=box.ROUNDED)
    table.add_column("Name", style="cyan")
    table.add_column("Base URL", style="green")
    table.add_column("Default Model", style="yellow")
    table.add_column("Available Models", style="blue")
    table.add_column("Default", style="magenta")

    for name, provider_data in config.providers.items():
        is_default = "✓" if name == config.default_provider else ""
        model_count = len(provider_data.get("available_models", []))
        table.add_row(
            name,
            provider_data["base_url"],
            provider_data.get("default_model", "None"),
            str(model_count),
            is_default
        )

    console.print(table)


async def _test_provider(config):
    """Test provider connection."""
    if not config.providers:
        print_info("No providers configured")
        return

    provider_names = list(config.providers.keys())
    name = Prompt.ask("Provider to test", choices=provider_names)

    provider_data = config.providers[name]
    base_url = provider_data["base_url"]
    api_key = provider_data.get("api_key", "dummy")

    console.print(f"\n[yellow]Testing {name}...[/yellow]")

    with create_spinner() as progress:
        task = progress.add_task("Connecting...", total=None)
        try:
            is_accessible = await ModelDiscovery.test_endpoint(base_url, api_key)

            if is_accessible:
                print_success(f"✓ Connection to '{name}' successful!")

                progress.update(task, description="Fetching models...")
                models = await ModelDiscovery.discover_models(base_url, api_key)

                if models:
                    print_success(f"✓ Found {len(models)} models")

                    # Update available models
                    provider_data["available_models"] = [m["id"] for m in models]
                    config.providers[name] = provider_data

            else:
                print_error(f"✗ Could not connect to '{name}'")

        except Exception as e:
            print_error(f"✗ Error: {str(e)}")


def _remove_provider(config):
    """Remove a provider."""
    if not config.providers:
        print_info("No providers configured")
        return

    provider_names = list(config.providers.keys())
    name = Prompt.ask("Provider to remove", choices=provider_names)

    if Confirm.ask(f"Remove provider '{name}'?"):
        del config.providers[name]

        # Update default if removed
        if config.default_provider == name:
            if config.providers:
                config.default_provider = list(config.providers.keys())[0]
                print_info(f"Default provider changed to '{config.default_provider}'")
            else:
                config.default_provider = None

        print_success(f"✓ Provider '{name}' removed")


async def _configure_agent_models(config):
    """Configure models for agents and sub-agents."""
    if not config.providers:
        print_error("No providers configured! Add a provider first.")
        return

    console.print("\n[bold cyan]🤖 Configure Agent Models[/bold cyan]\n")

    # Initialize agent_models if not exists
    if not config.agent_models:
        config.agent_models = {}

    agent_name = Prompt.ask("Agent/Sub-agent name (e.g., 'main', 'code-reviewer', 'research')")

    # Select provider
    provider_names = list(config.providers.keys())
    provider_name = Prompt.ask("Provider", choices=provider_names, default=config.default_provider)

    provider_data = config.providers[provider_name]
    available_models = provider_data.get("available_models", [])

    if not available_models:
        print_error("No models available for this provider!")
        model = Prompt.ask("Enter model name manually")
    else:
        # Show available models
        console.print("\n[bold]Available models:[/bold]")
        for i, model in enumerate(available_models[:20], 1):
            console.print(f"{i}. {model}")

        if len(available_models) > 20:
            console.print(f"[dim]... and {len(available_models) - 20} more[/dim]")

        model = Prompt.ask(
            "\nModel to use",
            choices=available_models if len(available_models) < 20 else None,
            default=provider_data.get("default_model")
        )

    # Temperature
    temperature = float(Prompt.ask("Temperature", default="0.7"))

    # Create agent model config
    agent_config = AgentModelConfig(
        agent_name=agent_name,
        provider=provider_name,
        model=model,
        temperature=temperature
    )

    config.agent_models[agent_name] = agent_config.model_dump()
    print_success(f"✓ Configured model for agent '{agent_name}'")


def _view_agent_models(config):
    """View agent model assignments."""
    if not config.agent_models:
        print_info("No agent models configured")
        return

    console.print("\n")
    table = Table(title="Agent Model Assignments", box=box.ROUNDED)
    table.add_column("Agent/Sub-agent", style="cyan")
    table.add_column("Provider", style="green")
    table.add_column("Model", style="yellow")
    table.add_column("Temperature", style="blue")

    for agent_name, agent_data in config.agent_models.items():
        table.add_row(
            agent_name,
            agent_data["provider"],
            agent_data["model"],
            str(agent_data["temperature"])
        )

    console.print(table)


@app.command("list")
def list_providers(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile to use"),
):
    """List all configured model providers."""
    config = get_current_config()
    _list_providers(config)


@app.command("agents")
def list_agent_models(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Profile to use"),
):
    """List agent model assignments."""
    config = get_current_config()
    _view_agent_models(config)


if __name__ == "__main__":
    app()
