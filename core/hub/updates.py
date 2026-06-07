"""Check hub lockfile entries for newer upstream versions."""

from __future__ import annotations

from dataclasses import dataclass

from core.hub.clawhub import ClawHubClient
from core.hub.lockfile import HubEntry, HubLockfile


@dataclass
class HubUpdateAvailable:
    entry_id: str
    skill_name: str
    source: str
    installed_version: str | None
    latest_version: str
    install_spec: str


def check_hub_updates(lock: HubLockfile) -> list[HubUpdateAvailable]:
    """Return entries where a newer ClawHub version exists."""
    out: list[HubUpdateAvailable] = []
    client = ClawHubClient()

    for entry in lock.list_entries():
        if entry.source != "clawhub":
            continue
        try:
            latest = client.resolve_version(entry.slug, None)
        except Exception:
            continue
        if entry.version == latest:
            continue
        spec = f"clawhub:{entry.slug}@{latest}"
        out.append(
            HubUpdateAvailable(
                entry_id=entry.id,
                skill_name=entry.skill_name,
                source=entry.source,
                installed_version=entry.version,
                latest_version=latest,
                install_spec=spec,
            )
        )
    return out