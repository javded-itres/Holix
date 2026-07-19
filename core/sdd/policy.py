"""Soft gates for SDD (warnings, not hard blocks)."""

from __future__ import annotations

from pathlib import Path

from core.sdd.paths import changes_root
from core.sdd.store import SpecStore


def soft_gate_warning(workspace: Path | str, *, writing_path: str | None = None) -> str | None:
    """Return a short warning if product code is written without apply mode.

    Fluid SDD: never blocks; agent/UI can surface the text.
    """
    root = Path(workspace)
    # Ignore writes inside openspec itself
    if writing_path:
        norm = writing_path.replace("\\", "/")
        if "/openspec/" in f"/{norm}" or norm.startswith("openspec/") or norm.endswith("openspec"):
            return None

    cr = changes_root(root)
    if not cr.is_dir():
        return None

    store = SpecStore(root)
    if not store.is_initialized():
        return None

    try:
        changes = store.list_changes()
    except Exception:
        return None

    open_ready = [c for c in changes if c.get("apply_ready")]
    if not open_ready:
        return None

    missing_mode = [
        c["change_id"]
        for c in open_ready
        if not c.get("apply_mode")
    ]
    if missing_mode:
        ids = ", ".join(missing_mode[:5])
        return (
            f"SDD soft gate: open apply-ready change(s) without execution mode: {ids}. "
            "Ask the user self|subagents|hybrid, then sdd_set_apply_mode before coding."
        )
    return None
