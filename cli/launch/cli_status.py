"""Per-CLI status panel for ``holix launch <cli> status``."""

from __future__ import annotations

import shutil
from typing import Any

from core.external_cli.env import build_cli_env, resolve_model_for_slot
from core.external_cli.registry import get_cli_spec
from core.external_cli.store import ExternalCliStore
from rich.panel import Panel
from rich.table import Table

from cli.services.tmux_launcher import find_active_sessions_for_cli
from cli.utils.rich_console import console, print_info


def _mask_secret(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return "—"
    if len(text) <= 8:
        return "••••"
    return f"{text[:4]}…{text[-4:]}"


def show_cli_status(profile: str, cli_id: str, profile_config: Any) -> None:
    spec = get_cli_spec(cli_id)
    if spec is None:
        console.print(f"[red]Unknown CLI: {cli_id}[/red]")
        raise SystemExit(1)

    store = ExternalCliStore(profile)
    binding = store.get_binding(cli_id)
    sessions = find_active_sessions_for_cli(profile, cli_id)

    binary = None
    if binding and binding.command:
        binary = binding.command
    else:
        for name in spec.binary_names:
            binary = shutil.which(name)
            if binary:
                break

    model_slot = (
        binding.model_slot if binding else spec.default_model_slot
    )
    model = resolve_model_for_slot(profile_config, model_slot)
    env_preview = (
        build_cli_env(
            spec,
            model,
            profile=profile,
            extra_env=binding.extra_env if binding else None,
        )
        if model
        else {}
    )

    lines = [
        f"[bold]{spec.display_name}[/bold] [dim]({spec.cli_id})[/dim]",
        spec.description,
        "",
        f"Enabled:     {'yes' if binding and binding.enabled else 'no'}",
        f"Binary:      {binary or 'not installed'}",
        f"Model slot:  {model_slot}",
    ]
    if model:
        lines.extend([
            f"Model:       {model.model}",
            f"Provider:    {model.provider}",
            f"Base URL:    {model.base_url}",
            f"API key:     {_mask_secret(model.api_key)}",
        ])
    else:
        lines.append("Model:       [yellow]not configured — run holix models setup[/yellow]")

    if binding and binding.default_cwd:
        lines.append(f"Default CWD: {binding.default_cwd}")

    if spec.install_hint:
        lines.extend(["", f"Install: {spec.install_hint}"])
    if spec.docs_url:
        lines.append(f"Docs:    {spec.docs_url}")

    console.print(Panel("\n".join(lines), title=f"holix launch {cli_id} status", border_style="cyan"))

    if env_preview:
        env_table = Table(title="Environment passed to CLI", show_header=True)
        env_table.add_column("Variable", style="cyan")
        env_table.add_column("Value")
        for key in sorted(env_preview):
            value = env_preview[key]
            if "key" in key.lower() or "token" in key.lower() or "secret" in key.lower():
                value = _mask_secret(value)
            env_table.add_row(key, value)
        console.print(env_table)

    if sessions:
        sess_table = Table(title=f"Active sessions ({len(sessions)})", show_header=True)
        sess_table.add_column("ID", style="cyan")
        sess_table.add_column("tmux")
        sess_table.add_column("Model")
        sess_table.add_column("CWD")
        sess_table.add_column("Win")
        for session in sessions:
            sess_table.add_row(
                session.session_id,
                session.tmux_session,
                session.model_name or session.model_slot,
                session.cwd,
                str(session.window_index),
            )
        console.print(sess_table)
        print_info(f"Open CLI: holix launch {cli_id}")
        print_info(f"Attach:   holix launch attach {sessions[-1].tmux_session}")
    else:
        print_info(f"No running session. Start: holix launch {cli_id} --detach")
        print_info(f"Status does not start the CLI — use launch or restart.")