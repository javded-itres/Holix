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
from core.models.catalog import (
    get_provider_preset,
    list_provider_presets,
    resolve_preset_base_url,
)
from core.models.discovery import ModelDiscovery
from core.models.provider import ProviderConfig, ModelProvider
from core.models.selector import AgentModelConfig
from core.models.profile_cleanup import profile_has_llm_config, remove_provider_from_profile
from core.models.setup_helpers import (
    add_preset_to_config,
    discover_and_select_default_model,
    prompt_host_for_preset,
    resolve_preset_api_key_interactive,
    resolve_api_key_for_preset,
)

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
        console.print("1. Add provider (catalog preset)")
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
            _remove_provider(config, profile=profile, save=False)
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


def _print_preset_catalog() -> None:
    table = Table(title="Popular providers", box=box.ROUNDED)
    table.add_column("#", style="dim")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Auth", style="yellow")
    table.add_column("Env variable", style="green")
    table.add_column("Host", style="dim")
    presets = list_provider_presets()
    for i, p in enumerate(presets, 1):
        auth = p.auth_type if p.auth_type != "bearer" else "API key"
        host_col = (
            f"{p.host_env} (:{p.default_port})"
            if p.configurable_host
            else "—"
        )
        table.add_row(str(i), p.id, p.display_name, auth, p.api_key_env, host_col)
    console.print(table)
    console.print(
        "\n[dim]Store secrets as ${ENV:VAR} in config.yaml. "
        "OpenRouter/Anthropic-via-OR need OPENROUTER_API_KEY + optional OPENROUTER_HTTP_REFERER.[/dim]\n"
    )


async def _add_provider(config):
    """Add a new model provider from catalog or custom URL."""
    console.print("\n[bold cyan]➕ Add Provider[/bold cyan]\n")
    _print_preset_catalog()

    presets = list_provider_presets()
    preset_choices = [str(i) for i in range(1, len(presets) + 1)] + ["custom"]
    choice = Prompt.ask(
        "Choose preset # or 'custom'",
        choices=preset_choices,
        default="1",
    )

    if choice != "custom":
        preset = presets[int(choice) - 1]
        if preset.id in config.providers:
            print_error(f"Provider '{preset.id}' already exists!")
            return
        if preset.notes:
            console.print(f"[dim]{preset.notes}[/dim]\n")
        import os

        api_key = resolve_preset_api_key_interactive(preset, console=console)
        if preset.auth_type != "none" and preset.api_key_env in os.environ:
            print_info(f"Using ${preset.api_key_env} from environment")
        custom_name = Prompt.ask("Provider name in profile", default=preset.id)
        host_arg: str | None = None
        if preset.configurable_host:
            if preset.host_env and preset.host_env in os.environ and os.environ[preset.host_env].strip():
                base = resolve_preset_base_url(preset)
                print_info(f"Host from {preset.host_env}: {base}")
            else:
                host_arg = prompt_host_for_preset(preset, console=console)
                print_info(f"Using base URL: {host_arg}")
        base_url = resolve_preset_base_url(preset, host=host_arg)
        store_key = (
            resolve_api_key_for_preset(preset, use_env_value=True)
            if preset.api_key_env in os.environ and os.environ.get(preset.api_key_env, "").strip()
            else (
                preset.api_key_placeholder
                if api_key.startswith("${") or api_key == preset.api_key_placeholder
                else api_key
            )
        )
        console.print(f"\n[bold]Connecting to {preset.display_name}…[/bold]")
        probe_ok, models, err, default_model = await discover_and_select_default_model(
            preset,
            base_url,
            api_key,
            console=console,
            interactive=True,
        )
        if not probe_ok and default_model is None:
            print_error(err or "Could not reach API")
            return
        with create_spinner() as progress:
            progress.add_task(f"Saving {preset.display_name}...", total=None)
            ok, msg = await add_preset_to_config(
                config,
                preset.id,
                provider_name=custom_name,
                api_key=store_key,
                host=host_arg,
                default_model=default_model,
                discovered_models=models if probe_ok else None,
                skip_probe=True,
            )
        if ok:
            print_success(f"✓ {msg}")
            if config.default_provider == custom_name:
                print_success(f"✓ Set '{custom_name}' as default provider")
        else:
            print_error(msg)
        return

    await _add_provider_custom(config)


async def _add_provider_custom(config):
    """Add provider with manual URL and API key."""
    name = Prompt.ask("Provider name (e.g., 'my-proxy')")
    if name in config.providers:
        print_error(f"Provider '{name}' already exists!")
        return

    base_url = Prompt.ask("Base URL", default="http://localhost:11434/v1")
    api_key = Prompt.ask("API key (Enter for 'dummy')", default="dummy")
    auth_type = Prompt.ask(
        "Auth type",
        choices=["bearer", "openrouter", "none"],
        default="bearer",
    )
    metadata: dict = {"auth_type": auth_type}
    if auth_type == "openrouter":
        metadata["http_referer"] = "${OPENROUTER_HTTP_REFERER}"
        metadata["x_title"] = "Helix"

    console.print("\n[yellow]Testing connection...[/yellow]")

    with create_spinner() as progress:
        task = progress.add_task("Connecting to provider...", total=None)
        try:
            is_accessible, _, _ = await probe_provider(base_url, api_key, metadata)
            if not is_accessible:
                print_error("✗ Could not connect to provider!")
                if not Confirm.ask("Add provider anyway?"):
                    return

            progress.update(task, description="Discovering models...")
            models = await ModelDiscovery.discover_models(base_url, api_key, metadata=metadata)

            if models:
                print_success(f"✓ Found {len(models)} models")

                # Display models
                table = Table(title="Available Models", box=box.ROUNDED)
                table.add_column("Model ID", style="cyan")
                table.add_column("Context", style="magenta")
                table.add_column("Owned By", style="green")

                # Build model_contexts mapping
                model_contexts = {}
                for model in models[:20]:  # Show first 20
                    ctx = model.get("context_length")
                    ctx_str = f"{ctx // 1000}k" if ctx else "?"
                    table.add_row(model["id"], ctx_str, model.get("owned_by", "unknown"))
                    if ctx:
                        model_contexts[model["id"]] = ctx

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
                    available_models=model_ids,
                    model_contexts=model_contexts,
                    metadata=metadata,
                )

                config.providers[name] = provider_config.model_dump()
                config.models_via_providers = True

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
                        metadata=metadata,
                    )
                    config.providers[name] = provider_config.model_dump()
                    config.models_via_providers = True
                    print_success(f"✓ Provider '{name}' added")

        except Exception as e:
            print_error(f"✗ Error: {str(e)}")
            if Confirm.ask("Add provider anyway?"):
                provider_config = ProviderConfig(
                    name=name,
                    base_url=base_url,
                    api_key=api_key,
                    metadata=metadata,
                )
                config.providers[name] = provider_config.model_dump()
                config.models_via_providers = True


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
    metadata = provider_data.get("metadata") or {}

    console.print(f"\n[yellow]Testing {name}...[/yellow]")

    with create_spinner() as progress:
        task = progress.add_task("Connecting...", total=None)
        try:
            is_accessible = await ModelDiscovery.test_endpoint(
                base_url, api_key, metadata=metadata
            )

            if is_accessible:
                print_success(f"✓ Connection to '{name}' successful!")

                progress.update(task, description="Fetching models...")
                models = await ModelDiscovery.discover_models(
                    base_url, api_key, metadata=metadata
                )

                if models:
                    print_success(f"✓ Found {len(models)} models")

                    # Update available models
                    provider_data["available_models"] = [m["id"] for m in models]
                    config.providers[name] = provider_data

            else:
                print_error(f"✗ Could not connect to '{name}'")

        except Exception as e:
            print_error(f"✗ Error: {str(e)}")


def _remove_provider(config, *, profile: Optional[str] = None, save: bool = False) -> bool:
    """Remove a provider and clean agent_models / legacy LLM fields."""
    if not config.providers:
        print_info("No providers configured")
        return False

    provider_names = list(config.providers.keys())
    name = Prompt.ask("Provider to remove", choices=provider_names)

    if not Confirm.ask(f"Remove provider '{name}'?"):
        return False

    for note in remove_provider_from_profile(config, name):
        print_info(note)

    if not profile_has_llm_config(config):
        print_info("No LLM configured. Run: helix models add <preset>  or  helix models setup")

    if save and profile:
        get_profile_manager().save_profile(profile, config)
        print_success("Configuration saved")
    else:
        print_success(f"✓ Provider '{name}' removed (save profile to persist)")

    return True


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


@app.command("presets")
def list_presets():
    """List built-in provider presets (OpenAI, OpenRouter, DeepSeek, Kimi, Grok, …)."""
    _print_preset_catalog()
    console.print("[dim]Add: helix models add openai[/dim]")


@app.command("add")
def add_preset(
    preset_id: str = typer.Argument(..., help="Preset id: openai, openrouter, ollama, litellm, vllm, …"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p"),
    name: Optional[str] = typer.Option(None, "--name", help="Profile provider name (default: preset id)"),
    host: Optional[str] = typer.Option(
        None,
        "--host",
        help="Host for ollama/litellm/vllm: IP, host:port, or full URL (e.g. 192.168.1.10:11434)",
    ),
    port: Optional[int] = typer.Option(None, "--port", help="Port if --host is hostname only"),
    skip_test: bool = typer.Option(False, "--skip-test", help="Skip connection test"),
):
    """Add a provider from the built-in catalog."""
    asyncio.run(_add_preset_cli(preset_id, profile, name, host, port, skip_test))


async def _add_preset_cli(
    preset_id: str,
    profile: Optional[str],
    name: Optional[str],
    host: Optional[str],
    port: Optional[int],
    skip_test: bool,
) -> None:
    if profile:
        from cli.core import init_profile

        init_profile(profile)
    config = get_current_config()
    manager = get_profile_manager()
    prof = profile or get_current_profile()

    preset = get_provider_preset(preset_id)
    if not preset:
        print_error(f"Unknown preset '{preset_id}'. Run: helix models presets")
        raise typer.Exit(1)

    import os

    api_key = resolve_preset_api_key_interactive(preset, console=console)
    if preset.auth_type != "none" and preset.api_key_env in os.environ:
        print_info(f"Using ${preset.api_key_env} from environment (stored as placeholder)")

    host_arg = host
    if preset.configurable_host and not host_arg and not (
        preset.host_env and os.environ.get(preset.host_env, "").strip()
    ):
        host_arg = prompt_host_for_preset(preset, console=console)

    base_url = resolve_preset_base_url(preset, host=host_arg, port=port)
    store_key = (
        resolve_api_key_for_preset(preset, use_env_value=True)
        if preset.api_key_env in os.environ and os.environ.get(preset.api_key_env, "").strip()
        else (
            preset.api_key_placeholder
            if api_key.startswith("${") or api_key == preset.api_key_placeholder
            else api_key
        )
    )

    default_model: str | None = None
    discovered: list[dict[str, Any]] | None = None
    if not skip_test:
        console.print(f"\n[bold]Fetching models from {preset.display_name}…[/bold]")
        probe_ok, discovered, err, default_model = await discover_and_select_default_model(
            preset,
            base_url,
            api_key,
            console=console,
            interactive=sys.stdin.isatty(),
        )
        if not probe_ok and default_model is None:
            print_error(err or "Could not reach API")
            raise typer.Exit(1)
        if not probe_ok:
            print_info("Using catalog model list (API unreachable)")

    with create_spinner():
        ok, msg = await add_preset_to_config(
            config,
            preset.id,
            provider_name=name,
            api_key=store_key,
            host=host_arg,
            port=port,
            skip_probe=True,
            default_model=default_model,
            discovered_models=discovered,
        )
    if not ok:
        print_error(msg)
        raise typer.Exit(1)
    manager.save_profile(prof, config)
    print_success(msg)


@app.command("remove")
def remove_provider_cmd(
    name: str = typer.Argument(..., help="Provider name to remove"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Remove a provider and clean related agent_models assignments."""
    if profile:
        from cli.core import init_profile

        init_profile(profile)
    config = get_current_config()
    prof = profile or get_current_profile()
    manager = get_profile_manager()

    if name not in (config.providers or {}):
        print_error(f"Provider '{name}' not found")
        raise typer.Exit(1)

    if not yes and not Confirm.ask(f"Remove provider '{name}'?"):
        raise typer.Exit(0)

    for note in remove_provider_from_profile(config, name):
        print_info(note)
    manager.save_profile(prof, config)
    print_success(f"Provider '{name}' removed from profile '{prof}'")
    if not profile_has_llm_config(config):
        print_info("No LLM configured. Run: helix models add <preset>")


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
