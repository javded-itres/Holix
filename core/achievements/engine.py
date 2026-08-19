"""Evaluate and persist skill-hygiene achievements next to the skills dir."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.achievements.catalog import ACHIEVEMENTS

_COUNTERS = (
    "skills_approved",
    "skills_patched",
    "skills_reused",
    "skills_learned_approved",
    "skills_refused",
    "main_autoassigns",
    "skills_archived",
)


def achievements_root(skills_dir: Path | str) -> Path:
    return Path(skills_dir).parent / "achievements"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        raw = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


class AchievementStore:
    """Sidecar at ``<data>/achievements/state.json``. Never touches the prompt."""

    def __init__(self, skills_dir: Path | str):
        self.skills_dir = Path(skills_dir)
        self.root = achievements_root(self.skills_dir)
        self.path = self.root / "state.json"

    def _empty(self) -> dict[str, Any]:
        return {
            "epoch": _iso(_utc_now()),
            "counters": {key: 0 for key in _COUNTERS},
            "unlocks": {},
        }

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._empty()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._empty()
        if not isinstance(data, dict):
            return self._empty()
        data.setdefault("epoch", _iso(_utc_now()))
        counters = data.setdefault("counters", {})
        for key in _COUNTERS:
            counters.setdefault(key, 0)
        data.setdefault("unlocks", {})
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def derived_counters(self, data: dict[str, Any]) -> dict[str, int]:
        counters = {key: int(data.get("counters", {}).get(key) or 0) for key in _COUNTERS}
        epoch = _parse_iso(data.get("epoch")) or _utc_now()
        days = max(0, int((_utc_now() - epoch).total_seconds() // 86400))
        if int(counters.get("main_autoassigns") or 0) == 0:
            counters["days_without_main_assign"] = days
        else:
            counters["days_without_main_assign"] = 0
        return counters

    def evaluate(self, data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Return (evaluated catalog, newly unlocked rows)."""
        counters = self.derived_counters(data)
        unlocks = data.setdefault("unlocks", {})
        now = _iso(_utc_now())
        evaluated: list[dict[str, Any]] = []
        newly: list[dict[str, Any]] = []
        for definition in ACHIEVEMENTS:
            metric = str(definition["metric"])
            progress = int(counters.get(metric) or 0)
            tiers = list(definition.get("tiers") or [])
            achieved = [t for t in tiers if progress >= int(t["threshold"])]
            pending = [t for t in tiers if progress < int(t["threshold"])]
            tier = achieved[-1]["name"] if achieved else None
            next_tier = pending[0]["name"] if pending else None
            next_threshold = (
                int(pending[0]["threshold"])
                if pending
                else (int(tiers[-1]["threshold"]) if tiers else 1)
            )
            unlocked = bool(achieved)
            discovered = progress > 0 or not definition.get("secret")
            if definition.get("secret") and not discovered:
                state = "secret"
            elif unlocked:
                state = "unlocked"
            else:
                state = "discovered"
            prev = unlocks.get(definition["id"])
            if unlocked and not prev:
                unlocks[definition["id"]] = {
                    "unlocked_at": now,
                    "tier": tier,
                }
                newly.append(
                    {
                        "id": definition["id"],
                        "name": definition["name"],
                        "name_ru": definition.get("name_ru"),
                        "tier": tier,
                    }
                )
            elif unlocked and prev and prev.get("tier") != tier:
                prev["tier"] = tier
                newly.append(
                    {
                        "id": definition["id"],
                        "name": definition["name"],
                        "name_ru": definition.get("name_ru"),
                        "tier": tier,
                    }
                )
            item = {
                **definition,
                "progress": progress,
                "tier": tier,
                "next_tier": next_tier,
                "next_threshold": next_threshold,
                "unlocked": unlocked,
                "state": state,
                "unlocked_at": (unlocks.get(definition["id"]) or {}).get("unlocked_at"),
            }
            if state == "secret":
                item["name"] = "???"
                item["name_ru"] = "???"
                item["description"] = "Secret until the matching signal appears."
                item["description_ru"] = "Секрет, пока не появится нужный сигнал."
            evaluated.append(item)
        return evaluated, newly

    def bump(
        self,
        metric: str,
        n: int = 1,
        *,
        evidence: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if metric not in _COUNTERS or n <= 0:
            return []
        data = self.load()
        data["counters"][metric] = int(data["counters"].get(metric) or 0) + int(n)
        if evidence:
            data.setdefault("evidence", {})[metric] = evidence
        _, newly = self.evaluate(data)
        self.save(data)
        return newly

    def snapshot(self) -> dict[str, Any]:
        data = self.load()
        evaluated, _newly = self.evaluate(data)
        self.save(data)
        unlocked = [a for a in evaluated if a.get("unlocked")]
        return {
            "achievements": evaluated,
            "counters": self.derived_counters(data),
            "epoch": data.get("epoch"),
            "unlocked_count": len(unlocked),
            "total_count": len(evaluated),
        }


def record_skill_signal(
    skills_dir: Path | str,
    signal: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Map a skill-lifecycle signal onto counters. Unknown signals are ignored."""
    store = AchievementStore(skills_dir)
    mapping = {
        "approved": "skills_approved",
        "patched": "skills_patched",
        "reused": "skills_reused",
        "learned_approved": "skills_learned_approved",
        "refused": "skills_refused",
        "main_assigned": "main_autoassigns",
        "archived": "skills_archived",
    }
    metric = mapping.get(signal)
    if not metric:
        return []
    return store.bump(metric, evidence=evidence)
