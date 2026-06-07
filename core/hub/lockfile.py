"""Track externally installed skills."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class HubEntry:
    id: str
    source: str
    slug: str
    version: str | None
    install_path: str
    skill_name: str
    installed_at: str
    install_spec: str | None = None
    marketplace: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HubLockfile:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._entries: dict[str, HubEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for item in data.get("entries", []):
                item = dict(item)
                item.setdefault("install_spec", None)
                item.setdefault("marketplace", None)
                entry = HubEntry(**{k: v for k, v in item.items() if k in HubEntry.__dataclass_fields__})
                self._entries[entry.id] = entry
        except Exception:
            self._entries = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "entries": [e.to_dict() for e in sorted(self._entries.values(), key=lambda x: x.id)],
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list_entries(self) -> list[HubEntry]:
        return list(self._entries.values())

    def get(self, entry_id: str) -> HubEntry | None:
        return self._entries.get(entry_id)

    def upsert(self, entry: HubEntry) -> None:
        self._entries[entry.id] = entry
        self.save()

    def remove(self, entry_id: str) -> bool:
        if entry_id not in self._entries:
            return False
        del self._entries[entry_id]
        self.save()
        return True

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()