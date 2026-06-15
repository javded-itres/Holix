"""Assign external CLIs to Holix sub-agent types (``agent_slot`` in bindings)."""

from __future__ import annotations

from dataclasses import dataclass

from core.external_cli.access import normalize_agent_slot
from core.external_cli.registry import get_cli_spec, list_cli_specs
from core.external_cli.store import ExternalCliBinding, ExternalCliStore
from core.subagents.registry import list_available_subagents


@dataclass(slots=True)
class CliAssignmentRow:
    cli_id: str
    display_name: str
    description: str
    enabled: bool
    agent_slot: str
    model_slot: str
    binary: str | None
    assigned: bool


def subagent_type_choices(*, profile: str | None = None) -> list[tuple[str, str]]:
    """Sub-agent types: (id, short description)."""
    return [
        (item["name"], item.get("description") or item["name"])
        for item in list_available_subagents(profile=profile)
    ]


def assigned_agent_slot(binding: ExternalCliBinding | None) -> str:
    if binding is None:
        return ""
    slot = normalize_agent_slot(binding.agent_slot)
    if not slot or slot == "main":
        return ""
    return slot


def list_cli_assignment_rows(
    profile: str,
    *,
    resolve_binary,
) -> list[CliAssignmentRow]:
    store = ExternalCliStore(profile)
    bindings = store.load_bindings()
    rows: list[CliAssignmentRow] = []
    for spec in list_cli_specs():
        binding = bindings.get(spec.cli_id)
        binary = None
        if binding and binding.command.strip():
            binary = binding.command.strip()
        else:
            binary = resolve_binary(spec)
        agent_slot = assigned_agent_slot(binding)
        rows.append(
            CliAssignmentRow(
                cli_id=spec.cli_id,
                display_name=spec.display_name,
                description=spec.description,
                enabled=bool(binding.enabled) if binding else False,
                agent_slot=agent_slot,
                model_slot=(binding.model_slot if binding else spec.default_model_slot),
                binary=binary,
                assigned=bool(agent_slot),
            )
        )
    return rows


def assign_cli_to_subagent(
    profile: str,
    cli_id: str,
    agent_type: str,
) -> ExternalCliBinding:
    spec = get_cli_spec(cli_id)
    if spec is None:
        raise ValueError(f"Unknown CLI: {cli_id}")
    agent = normalize_agent_slot(agent_type)
    if not agent or agent == "main":
        raise ValueError(f"Invalid sub-agent type: {agent_type}")
    known_types = {name for name, _ in subagent_type_choices(profile=profile)}
    if agent not in known_types:
        known = ", ".join(sorted(known_types))
        raise ValueError(f"Unknown sub-agent '{agent_type}'. Available: {known}")

    store = ExternalCliStore(profile)
    binding = store.get_binding(cli_id) or ExternalCliBinding(
        cli_id=spec.cli_id,
        model_slot=spec.default_model_slot,
    )
    binding.agent_slot = agent
    binding.enabled = True
    store.upsert_binding(binding)
    return binding


def unassign_cli_subagent(profile: str, cli_id: str) -> ExternalCliBinding | None:
    spec = get_cli_spec(cli_id)
    if spec is None:
        raise ValueError(f"Unknown CLI: {cli_id}")
    store = ExternalCliStore(profile)
    binding = store.get_binding(cli_id)
    if binding is None:
        return None
    binding.agent_slot = ""
    store.upsert_binding(binding)
    return binding