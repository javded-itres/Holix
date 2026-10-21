"""One next command for an SDD change, so resume does not rely on memory."""

from __future__ import annotations

from core.sdd.models import ChangeStatus


def next_action(
    status: ChangeStatus,
    *,
    understanding: dict | None = None,
    review_errors: list[str] | None = None,
) -> str:
    """Name the next SDD step. Checked tasks are not an archive."""
    und = understanding or {}
    if und.get("enabled") and und.get("status") == "clarifying":
        return (
            "Next: read main specs and the code you would change, then "
            "sdd_update_understanding. Do not fill artifacts yet."
        )
    if und.get("enabled") and und.get("status") == "ready":
        return "Next: sdd_confirm_understanding after the user agrees to proceed."

    if not status.artifacts.get("proposal"):
        return "Next: sdd_write_artifact proposal (Why / What / Impact)."
    if not status.skip_specs and not status.artifacts.get("specs"):
        return (
            "Next: sdd_write_artifact specs for one domain as soon as it is drafted "
            "(ADDED/MODIFIED/REMOVED). A refactor or docs change with no behavior "
            "change sets skip_specs=true on sdd_create_change or sdd_write_artifact."
        )
    if not status.apply_ready:
        detail = "; ".join(status.missing) if status.missing else "change is not apply-ready"
        return f"Next: {detail}"
    if status.tasks_complete and review_errors:
        return (
            "Next: fix the spec delta (" + review_errors[0] + ") before sdd_archive. "
            "Titles that differ only by case are refused."
        )
    if status.tasks_complete:
        return (
            "Next: tracked tasks are complete. Show delta_review to the user and call "
            "sdd_archive only after they agree. Do not call the change ready to archive."
        )
    if not status.apply_mode:
        return (
            "Next: sdd_request_apply_mode, ask the user self|subagents|hybrid, "
            "then sdd_set_apply_mode. Do not write product code yet."
        )
    return (
        "Next: sdd_apply, then sdd_check_task as each task is done. "
        "Checked boxes are not an archive."
    )
