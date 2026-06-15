"""Interactive setup for external coding CLIs."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.external_cli.platform import ensure_launch_platform, tmux_available
from core.external_cli.registry import (
    EXTERNAL_CLI_REGISTRY,
    ExternalCliSpec,
    format_cli_id_choices,
    list_cli_specs,
    resolve_cli_selection,
)
from core.external_cli.store import ExternalCliBinding, ExternalCliStore
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from cli.utils.rich_console import console, print_error, print_info, print_success, print_warning


def _install_path_dirs() -> str:
    home = Path.home()
    dirs: list[str] = []
    for spec in list_cli_specs():
        for raw in spec.binary_paths:
            parent = str(Path(raw).expanduser().parent)
            if parent not in dirs:
                dirs.append(parent)
    for sub in (".local/bin", ".opencode/bin", ".grok/bin"):
        candidate = str(home / sub)
        if candidate not in dirs:
            dirs.append(candidate)
    current = os.environ.get("PATH", "")
    return os.pathsep.join([*dirs, current]) if dirs else current


def _binary_installed(spec: ExternalCliSpec) -> str | None:
    search_path = _install_path_dirs()
    for name in spec.binary_names:
        path = shutil.which(name, path=search_path)
        if path:
            return path
    for raw in spec.binary_paths:
        candidate = Path(raw).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _try_install(spec_id: str) -> bool:
    spec = EXTERNAL_CLI_REGISTRY[spec_id]
    if not spec.install_commands:
        print_info(spec.install_hint or "No automatic install available.")
        return False
    for cmd in spec.install_commands:
        tool = cmd[0]
        if shutil.which(tool) is None:
            print_warning(f"Skip install: `{tool}` not found on PATH")
            return False
        display_cmd = " ".join(cmd[2:]) if len(cmd) >= 3 and cmd[1] in {"-c", "-lc"} else " ".join(cmd)
        print_info(f"Running: {display_cmd}")
        try:
            subprocess.run(cmd, check=True, timeout=600)
            if _binary_installed(spec):
                print_success(f"Installed {spec.display_name}")
                return True
            print_warning(
                f"Install finished but `{spec.binary_names[0]}` not found yet. "
                "Open a new shell or add the install directory to PATH."
            )
            return False
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            print_error(f"Install failed: {exc}")
            return False
    return False


def run_launch_setup(profile: str, profile_config: Any, *, yes: bool = False) -> None:
    ensure_launch_platform()
    if not tmux_available():
        print_error("tmux is required. Install: brew install tmux  OR  apt install tmux")
        raise SystemExit(1)

    console.print()
    console.print(Panel.fit(
        "[bold cyan]External CLI Launch Setup[/bold cyan]\n\n"
        "Configure coding agents (Claude Code, OpenCode, GigaCode, …) in tmux.\n"
        "Models are taken from your Holix profile (holix models setup).",
        border_style="cyan",
    ))
    console.print()

    store = ExternalCliStore(profile)
    bindings = store.load_bindings()
    agent_slots = _agent_slots(profile_config)

    table = Table(title=f"Profile: {profile}", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("CLI")
    table.add_column("Status")
    table.add_column("Binary")
    table.add_column("Model slot")

    for spec in list_cli_specs():
        path = _binary_installed(spec)
        binding = bindings.get(spec.cli_id)
        if binding and binding.command:
            path = binding.command
        enabled = binding.enabled if binding else False
        slot = binding.model_slot if binding else spec.default_model_slot
        status = "[green]enabled[/green]" if enabled else "[dim]disabled[/dim]"
        if not path:
            status = "[yellow]not installed[/yellow]"
        table.add_row(spec.cli_id, spec.display_name, status, path or "—", slot)

    console.print(table)
    console.print()

    if yes:
        to_configure = [s.cli_id for s in list_cli_specs()]
    else:
        id_hint = format_cli_id_choices()
        raw = Prompt.ask(
            f"Configure which CLI? (id, name, or 'all'; e.g. {id_hint})",
            default="all",
        )
        to_configure, unknown = resolve_cli_selection(raw)
        for token in unknown:
            print_warning(
                f"Unknown CLI: {token!r}. Use id ({id_hint}) or display name (e.g. Claude Code)."
            )
        if not to_configure:
            print_error("Nothing to configure. Try: claude  or  Claude Code  or  all")
            raise SystemExit(1)

    for cli_id in to_configure:
        spec = EXTERNAL_CLI_REGISTRY.get(cli_id)
        if spec is None:
            continue

        console.print(f"\n[bold]{spec.display_name}[/bold] — {spec.description}")

        path = _binary_installed(spec)
        if not path:
            print_warning(f"Binary not found ({', '.join(spec.binary_names)})")
            if spec.install_commands:
                should_install = yes or Confirm.ask("Try automatic install?", default=False)
                if should_install:
                    _try_install(cli_id)
                    path = _binary_installed(spec)
            elif spec.install_hint:
                print_info(spec.install_hint)

        binding = bindings.get(cli_id) or ExternalCliBinding(
            cli_id=cli_id,
            model_slot=spec.default_model_slot,
            agent_slot=spec.default_model_slot,
        )

        if yes:
            binding.enabled = bool(path)
        else:
            binding.enabled = Confirm.ask("Enable for this profile?", default=bool(path))

        if binding.enabled:
            if path:
                binding.command = path
            else:
                custom = Prompt.ask(
                    "Path to binary",
                    default=binding.command or spec.binary_names[0],
                )
                binding.command = custom.strip()

            if agent_slots:
                slot_choices = ", ".join(agent_slots)
                slot = Prompt.ask(
                    f"Model slot ({slot_choices})",
                    default=binding.model_slot or spec.default_model_slot,
                )
                binding.model_slot = slot.strip() or spec.default_model_slot

            subagent_choices = _subagent_slot_choices(profile)
            default_agent_slot = binding.agent_slot or spec.default_model_slot
            if default_agent_slot == "main":
                default_agent_slot = spec.default_model_slot
            agent_slot = Prompt.ask(
                f"Assign to sub-agent ({', '.join(subagent_choices)})",
                default=default_agent_slot,
            ).strip() or default_agent_slot
            binding.agent_slot = agent_slot

            cwd = Prompt.ask(
                "Default working directory (optional)",
                default=binding.default_cwd or "",
            )
            binding.default_cwd = cwd.strip()

        bindings[cli_id] = binding
        store.upsert_binding(binding)
        print_success(f"Saved binding for {spec.display_name}")

    console.print()
    print_info("Open CLI: holix launch claude  |  Status: holix launch claude status  |  Sessions: holix launch sessions")


def _subagent_slot_choices(profile: str | None = None) -> list[str]:
    from core.subagents.registry import list_available_subagents

    return sorted(item["name"] for item in list_available_subagents(profile=profile))


def _agent_slots(profile_config: Any) -> list[str]:
    slots = ["main"]
    agent_models = getattr(profile_config, "agent_models", None) or {}
    for name in sorted(agent_models.keys()):
        if name not in slots:
            slots.append(name)
    for spec in list_cli_specs():
        if spec.default_model_slot not in slots:
            slots.append(spec.default_model_slot)
    return slots