"""Per-profile SDD user preferences (understanding gate)."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from core.sdd.understanding import DEFAULT_THRESHOLD


class SddPrefs(BaseModel):
    version: int = 1
    understanding_gate_enabled: bool = False
    understanding_threshold: int = Field(default=DEFAULT_THRESHOLD, ge=1, le=100)


def prefs_path(profile: str) -> Path:
    from core.profile.names import profile_dir_for_name, validate_profile_name

    d = profile_dir_for_name(validate_profile_name(profile)) / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d / "sdd_prefs.json"


class SddPrefsStore:
    def __init__(self, profile: str = "default") -> None:
        from core.profile.names import validate_profile_name

        self.profile = validate_profile_name(profile)
        self._path = prefs_path(self.profile)

    def load(self) -> SddPrefs:
        if not self._path.exists():
            return SddPrefs()
        try:
            return SddPrefs.model_validate(json.loads(self._path.read_text(encoding="utf-8")))
        except Exception:
            return SddPrefs()

    def save(self, data: SddPrefs) -> SddPrefs:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(data.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return data

    def get(self) -> SddPrefs:
        return self.load()

    def update(
        self,
        *,
        understanding_gate_enabled: bool | None = None,
        understanding_threshold: int | None = None,
    ) -> SddPrefs:
        data = self.load()
        if understanding_gate_enabled is not None:
            data.understanding_gate_enabled = bool(understanding_gate_enabled)
        if understanding_threshold is not None:
            thr = int(understanding_threshold)
            data.understanding_threshold = max(1, min(100, thr))
        return self.save(data)
