"""Helpers for adding providers from catalog presets."""

from __future__ import annotations

import os
import sys
from typing import Any

from rich import box
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from core.models.catalog import (
    ProviderPreset,
    get_provider_preset,
    resolve_preset_base_url,
)
from core.models.discovery import ModelDiscovery
from core.models.provider import ProviderConfig


def prompt_verify_ssl(
    base_url: str,
    *,
    console: Console | None = None,
    default: bool = True,
) -> dict[str, Any]:
    """Ask whether to verify TLS when base URL uses HTTPS."""
    if not base_url.lower().startswith("https://"):
        return {}
    if not sys.stdin.isatty():
        return {}
    out = console or Console()
    if Confirm.ask("Verify SSL certificate?", default=default, console=out):
        return {}
    out.print("[yellow]TLS certificate verification disabled for this provider.[/yellow]")
    return {"verify_ssl": False}


def resolve_ssl_metadata_extra(
    base_url: str = "",
    *,
    no_verify_ssl: bool = False,
    console: Console | None = None,
) -> dict[str, Any]:
    """SSL metadata for provider setup (global --no-verify-ssl or per-URL prompt)."""
    if no_verify_ssl:
        return {"verify_ssl": False}
    if not base_url:
        return {}
    return prompt_verify_ssl(base_url, console=console)


def apply_ssl_override(
    metadata: dict[str, Any] | None,
    *,
    no_verify_ssl: bool = False,
) -> dict[str, Any]:
    """Merge session-level --no-verify-ssl into provider metadata for probes."""
    merged = dict(metadata or {})
    if no_verify_ssl:
        merged["verify_ssl"] = False
    return merged


def merge_provider_metadata(
    base: dict[str, Any] | None,
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(base or {})
    if extra:
        merged.update(extra)
    return merged


async def probe_provider(
    base_url: str,
    api_key: str,
    metadata: dict[str, Any] | None,
) -> tuple[bool, list[dict[str, Any]], str | None]:
    """Test endpoint and discover models. Returns (ok, models, error)."""
    try:
        ok = await ModelDiscovery.test_endpoint(base_url, api_key, metadata=metadata)
        if not ok:
            return False, [], "connection failed"
        models = await ModelDiscovery.discover_models(base_url, api_key, metadata=metadata)
        return True, models, None
    except Exception as e:
        return False, [], str(e)


def resolve_preset_api_key_interactive(
    preset: ProviderPreset,
    *,
    console: Console | None = None,
) -> str:
    """Resolve or prompt API key before probing external providers."""
    if preset.auth_type == "none":
        return "EMPTY" if preset.id == "vllm" else "ollama"

    if preset.api_key_env in os.environ and os.environ[preset.api_key_env].strip():
        return resolve_api_key_for_preset(preset, use_env_value=True)

    if not sys.stdin.isatty():
        return preset.api_key_placeholder

    out = console or Console()
    out.print(
        f"[dim]Set {preset.api_key_env} in .env or enter key now to list models.[/dim]"
    )
    entered = Prompt.ask(
        f"API key ({preset.api_key_env})",
        password=True,
        default=preset.api_key_placeholder,
    ).strip()
    if not entered:
        return preset.api_key_placeholder
    if entered.startswith("${"):
        return entered
    # Literal key: use for probe; store placeholder in profile unless user wants literal
    return entered


def resolve_api_key_for_preset(
    preset: ProviderPreset,
    *,
    use_env_value: bool = True,
    custom_key: str | None = None,
) -> str:
    """Pick API key: explicit value, live env, or ${ENV} placeholder for YAML."""
    if custom_key is not None and custom_key.strip():
        return custom_key.strip()
    if use_env_value and preset.api_key_env in os.environ and os.environ[preset.api_key_env].strip():
        return preset.api_key_placeholder
    if preset.auth_type == "none":
        return "EMPTY" if preset.id == "vllm" else "ollama"
    return preset.api_key_placeholder


def prompt_host_for_preset(preset: ProviderPreset, *, console: Any = None) -> str:
    """Interactive or env-based host resolution for Ollama / LiteLLM / vLLM."""
    import os

    if not preset.configurable_host:
        return preset.base_url

    if preset.host_env and os.environ.get(preset.host_env, "").strip():
        base = resolve_preset_base_url(preset)
        if console:
            console.print(f"[dim]Using {preset.host_env}={os.environ[preset.host_env].strip()}[/dim]")
        return base

    default_hint = f"{preset.default_host}:{preset.default_port}"
    if console is None:
        from rich.prompt import Prompt

        host_in = Prompt.ask(
            f"Host ({preset.display_name})",
            default=default_hint,
        )
    else:
        from rich.prompt import Prompt

        host_in = Prompt.ask(
            f"Host [dim]({preset.host_env} or URL, default {default_hint})[/dim]",
            default=default_hint,
        )
    return resolve_preset_base_url(preset, host=host_in)


def print_discovered_models_table(
    models: list[dict[str, Any]],
    *,
    console: Console | None = None,
    title: str = "Available models",
    max_rows: int = 40,
) -> None:
    """Print a Rich table of discovered models."""
    out = console or Console()
    if not models:
        out.print("[yellow]No models returned by the API.[/yellow]")
        return

    table = Table(title=title, box=box.ROUNDED)
    table.add_column("#", style="dim", justify="right")
    table.add_column("Model ID", style="cyan")
    table.add_column("Context", style="magenta")
    table.add_column("Owned by", style="green")

    shown = models[:max_rows]
    for i, model in enumerate(shown, 1):
        ctx = model.get("context_length")
        ctx_str = f"{int(ctx) // 1000}k" if ctx else "—"
        table.add_row(
            str(i),
            str(model.get("id", "")),
            ctx_str,
            str(model.get("owned_by", "—")),
        )
    out.print(table)
    if len(models) > max_rows:
        out.print(f"[dim]… and {len(models) - max_rows} more[/dim]")


def _catalog_models_as_rows(preset: ProviderPreset) -> list[dict[str, Any]]:
    return [
        {
            "id": mid,
            "context_length": preset.model_contexts.get(mid),
            "owned_by": "catalog",
        }
        for mid in preset.popular_models
    ]


def auto_pick_default_model(
    models: list[dict[str, Any]],
    preset: ProviderPreset,
) -> str | None:
    """Pick default model id from discovery or preset."""
    ids = [str(m.get("id", "")) for m in models if m.get("id")]
    if preset.default_model and preset.default_model in ids:
        return preset.default_model
    return ids[0] if ids else preset.default_model


def prompt_default_model_choice(
    models: list[dict[str, Any]],
    preset: ProviderPreset,
    *,
    console: Console | None = None,
) -> str | None:
    """Let user choose default model from discovered (or catalog) list."""
    ids = [str(m["id"]) for m in models if m.get("id")]
    if not ids:
        return preset.default_model

    out = console or Console()
    default_guess = auto_pick_default_model(models, preset) or ids[0]

    if len(ids) <= 12:
        choice = Prompt.ask(
            "Default model",
            choices=ids,
            default=default_guess,
            show_choices=True,
        )
        return choice

    out.print("[dim]Enter model id or # from the table above[/dim]")
    while True:
        raw = Prompt.ask("Default model", default=default_guess).strip()
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(ids):
                return ids[idx]
        if raw in ids:
            return raw
        out.print("[red]Unknown model — pick id or #[/red]")


async def discover_and_select_default_model(
    preset: ProviderPreset,
    base_url: str,
    api_key: str,
    *,
    console: Console | None = None,
    interactive: bool | None = None,
    metadata_extra: dict[str, Any] | None = None,
) -> tuple[bool, list[dict[str, Any]], str | None, str | None]:
    """Probe API, show models, return (ok, models, error, default_model_id)."""
    out = console or Console()
    if interactive is None:
        interactive = sys.stdin.isatty()

    metadata = merge_provider_metadata(preset.default_metadata(), metadata_extra)
    ok, models, err = await probe_provider(base_url, api_key, metadata)

    if ok and models:
        print_discovered_models_table(
            models,
            console=out,
            title=f"{preset.display_name} — models @ {base_url}",
        )
        if interactive:
            chosen = prompt_default_model_choice(models, preset, console=out)
        else:
            chosen = auto_pick_default_model(models, preset)
            out.print(f"[dim]Default model: {chosen}[/dim]")
        return True, models, None, chosen

    if preset.popular_models:
        catalog_rows = _catalog_models_as_rows(preset)
        out.print(
            f"[yellow]Could not list models from API ({err or 'connection failed'}). "
            f"Catalog defaults for {preset.display_name}:[/yellow]"
        )
        print_discovered_models_table(
            catalog_rows,
            console=out,
            title=f"{preset.display_name} — catalog models",
        )
        if interactive:
            chosen = prompt_default_model_choice(catalog_rows, preset, console=out)
        else:
            chosen = auto_pick_default_model(catalog_rows, preset)
        return False, [], err, chosen

    return False, [], err, None


def build_provider_entry(
    preset: ProviderPreset,
    *,
    name: str | None = None,
    api_key: str,
    base_url: str | None = None,
    discovered_models: list[dict[str, Any]] | None = None,
    default_model: str | None = None,
    metadata_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge discovery results with catalog defaults into a provider dict."""
    provider_name = name or preset.id
    model_contexts = dict(preset.model_contexts)
    available: list[str] = []

    if discovered_models:
        for m in discovered_models:
            mid = m.get("id")
            if mid and mid not in available:
                available.append(mid)
            ctx = m.get("context_length")
            if mid and ctx:
                model_contexts[mid] = int(ctx)

    for mid in preset.popular_models:
        if mid not in available:
            available.append(mid)

    if not available and preset.default_model:
        available = [preset.default_model]

    resolved_default = default_model or preset.default_model or (available[0] if available else None)
    resolved_url = base_url or preset.base_url
    meta = merge_provider_metadata(preset.default_metadata(), metadata_extra)
    if preset.configurable_host and preset.host_env:
        meta["host"] = resolved_url

    cfg = ProviderConfig(
        name=provider_name,
        base_url=resolved_url,
        api_key=api_key,
        default_model=resolved_default,
        available_models=available,
        model_contexts=model_contexts,
        metadata=meta,
    )
    return cfg.model_dump()


async def add_preset_to_config(
    config: Any,
    preset_id: str,
    *,
    provider_name: str | None = None,
    api_key: str | None = None,
    host: str | None = None,
    port: int | None = None,
    skip_probe: bool = False,
    default_model: str | None = None,
    discovered_models: list[dict[str, Any]] | None = None,
    metadata_extra: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Add a catalog preset to profile config. Returns (success, message)."""
    preset = get_provider_preset(preset_id)
    if preset is None:
        return False, f"Unknown preset: {preset_id}"

    name = provider_name or preset.id
    if name in (config.providers or {}):
        return False, f"Provider '{name}' already exists"

    key = resolve_api_key_for_preset(preset, custom_key=api_key)
    base_url = resolve_preset_base_url(preset, host=host, port=port)
    metadata = merge_provider_metadata(preset.default_metadata(), metadata_extra)

    models: list[dict[str, Any]] = list(discovered_models or [])
    if not skip_probe and not models:
        ok, models, err = await probe_provider(base_url, key, metadata)
        if not ok and not preset.popular_models:
            return False, f"{err or 'connection failed'} ({base_url})"
        if not ok and preset.popular_models:
            models = []

    entry = build_provider_entry(
        preset,
        name=name,
        api_key=key,
        base_url=base_url,
        discovered_models=models or None,
        default_model=default_model,
        metadata_extra=metadata_extra,
    )
    if not config.providers:
        config.providers = {}
    config.providers[name] = entry
    if hasattr(config, "models_via_providers"):
        config.models_via_providers = True

    if config.default_provider is None:
        config.default_provider = name

    n_models = len(entry.get("available_models") or [])
    model_label = entry.get("default_model") or "—"
    return (
        True,
        f"Provider '{name}' ({preset.display_name}) @ {base_url} — "
        f"default {model_label}, {n_models} model(s) in profile",
    )