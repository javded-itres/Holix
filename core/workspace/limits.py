"""Platform-managed per-profile limits (not user-editable)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.billing.tariffs import TariffLimits, default_tariff_id, limits_for_tariff
from core.profile_keys import profile_dir

LIMITS_FILENAME = "limits.json"


@dataclass(frozen=True, slots=True)
class ProfileLimits:
    version: int
    tariff_id: str
    workspace_max_bytes: int
    workspace_max_files: int
    source: str
    updated_at: str
    updated_by: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "tariff_id": self.tariff_id,
            "workspace_max_bytes": self.workspace_max_bytes,
            "workspace_max_files": self.workspace_max_files,
            "source": self.source,
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProfileLimits:
        return cls(
            version=int(data.get("version") or 1),
            tariff_id=str(data.get("tariff_id") or default_tariff_id()),
            workspace_max_bytes=int(data.get("workspace_max_bytes") or 0),
            workspace_max_files=int(data.get("workspace_max_files") or 0),
            source=str(data.get("source") or "platform"),
            updated_at=str(data.get("updated_at") or ""),
            updated_by=str(data.get("updated_by") or "platform"),
        )

    @classmethod
    def from_tariff(
        cls,
        tariff: TariffLimits,
        *,
        updated_by: str = "platform",
    ) -> ProfileLimits:
        return cls(
            version=1,
            tariff_id=tariff.tariff_id,
            workspace_max_bytes=tariff.workspace_max_bytes,
            workspace_max_files=tariff.workspace_max_files,
            source="platform",
            updated_at=datetime.now(UTC).isoformat(),
            updated_by=updated_by,
        )


def limits_path(profile: str) -> Path:
    return profile_dir(profile) / LIMITS_FILENAME


def load_profile_limits(profile: str) -> ProfileLimits | None:
    path = limits_path(profile)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ProfileLimits.from_dict(data)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def save_profile_limits(profile: str, limits: ProfileLimits) -> None:
    path = limits_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(limits.to_dict(), indent=2) + "\n", encoding="utf-8")


def ensure_profile_limits(profile: str, *, tariff_id: str | None = None) -> ProfileLimits:
    existing = load_profile_limits(profile)
    if existing is not None:
        return existing
    tariff = limits_for_tariff(tariff_id or default_tariff_id())
    limits = ProfileLimits.from_tariff(tariff)
    save_profile_limits(profile, limits)
    return limits


def set_profile_tariff(profile: str, tariff_id: str, *, updated_by: str = "admin") -> ProfileLimits:
    tariff = limits_for_tariff(tariff_id)
    limits = ProfileLimits.from_tariff(tariff, updated_by=updated_by)
    save_profile_limits(profile, limits)
    return limits