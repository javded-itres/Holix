"""Optional scheduled hub updates (ClawHub version drift)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.hub.importer import SkillImporter
from core.hub.lockfile import HubLockfile
from core.hub.updates import check_hub_updates


@dataclass
class HubAutoupdateResult:
    ran: bool
    reason: str
    updated: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def autoupdate_state_path(profile_dir: Path) -> Path:
    return Path(profile_dir) / "hub-autoupdate-state.json"


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _is_due(last_iso: str | None, interval_hours: float) -> bool:
    if not last_iso:
        return True
    try:
        last = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
    except Exception:
        return True
    elapsed_h = (datetime.now(timezone.utc) - last).total_seconds() / 3600.0
    return elapsed_h >= max(interval_hours, 0.25)


def run_hub_autoupdate(
    importer: SkillImporter,
    *,
    enabled: bool,
    interval_hours: float = 24.0,
    force: bool = False,
    dry_run: bool = False,
    full_reinstall: bool = False,
    state_path: Path | None = None,
) -> HubAutoupdateResult:
    """Apply ClawHub updates or reinstall all lock entries when due."""
    state_file = state_path or autoupdate_state_path(importer.skills_dir.parent)
    state = _load_state(state_file)

    if not force and not enabled:
        return HubAutoupdateResult(False, "disabled")

    if not force and not _is_due(state.get("last_run_at"), interval_hours):
        return HubAutoupdateResult(False, "not_due")

    updated: list[str] = []
    failed: list[str] = []

    if full_reinstall:
        targets = [(e.id, e.install_spec or importer._entry_to_spec(e)) for e in importer.lock.list_entries()]
    else:
        targets = [(u.entry_id, u.install_spec) for u in check_hub_updates(importer.lock)]

    if not targets and not full_reinstall:
        _save_state(state_file, {"last_run_at": datetime.now(timezone.utc).isoformat()})
        return HubAutoupdateResult(True, "nothing_to_update")

    if dry_run:
        names = [t[0] for t in targets if t[1]]
        return HubAutoupdateResult(True, "dry_run", updated=names)

    for entry_id, spec in targets:
        if not spec:
            failed.append(entry_id)
            continue
        try:
            outcome = importer.install(spec)
            updated.append(outcome.skill_name or entry_id)
        except Exception:
            failed.append(entry_id)

    _save_state(
        state_file,
        {
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": updated,
            "last_failed": failed,
        },
    )
    return HubAutoupdateResult(True, "completed", updated=updated, failed=failed)


def suggested_cron_line(profile: str = "default") -> str:
    from core.platform_compat import IS_WINDOWS, helix_home_display

    log_file = str(Path(helix_home_display()) / "logs" / "hub-autoupdate.log")
    cmd = f"helix hub autoupdate -p {profile} --force >> {log_file} 2>&1"
    if IS_WINDOWS:
        return f"Task Scheduler (daily 04:00): {cmd}"
    return f"0 4 * * * {cmd}"