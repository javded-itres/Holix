"""Who may launch external CLIs via the agent ``external_cli`` tool."""

from __future__ import annotations

from core.external_cli.store import ExternalCliBinding, ExternalCliStore


def normalize_agent_slot(slot: str) -> str:
    return (slot or "").strip().lower()


def binding_allows_subagent(binding: ExternalCliBinding, agent_type: str) -> bool:
    if not binding.enabled:
        return False
    assigned = normalize_agent_slot(binding.agent_slot)
    if not assigned or assigned == "main":
        return False
    return assigned == normalize_agent_slot(agent_type)


def list_external_cli_ids_for_subagent(profile: str, agent_type: str) -> list[str]:
    store = ExternalCliStore(profile)
    out: list[str] = []
    for cli_id, binding in store.load_bindings().items():
        if binding_allows_subagent(binding, agent_type):
            out.append(cli_id)
    return sorted(out)


def subagent_has_external_cli_assignment(profile: str, agent_type: str) -> bool:
    return bool(list_external_cli_ids_for_subagent(profile, agent_type))


def external_cli_launch_error(
    profile: str,
    cli_id: str,
    *,
    caller_agent_type: str,
) -> str | None:
    """Return an error message when launch is not allowed, else ``None``."""
    caller = normalize_agent_slot(caller_agent_type)
    if not caller or caller == "main":
        return (
            "Error: external_cli launch is only available to assigned sub-agents. "
            "Delegate the task with delegate_to_subagent, then let that sub-agent launch the CLI."
        )

    binding = ExternalCliStore(profile).get_binding(cli_id)
    if binding is None:
        return f"Error: {cli_id} is not configured for this profile. Run: holix launch setup"
    if not binding.enabled:
        return f"Error: {cli_id} is disabled for this profile. Enable it in holix launch setup."
    if not binding_allows_subagent(binding, caller):
        assigned = binding.agent_slot or "—"
        return (
            f"Error: {cli_id} is assigned to sub-agent '{assigned}', not '{caller_agent_type}'. "
            "Update the binding in holix launch setup or delegate to the assigned sub-agent."
        )
    return None