"""Deterministic prune for agent-created skills. No LLM, no deletes."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from core.skills.proposal import is_protected_skill

STALE_AFTER_DAYS = 30
ARCHIVE_AFTER_DAYS = 90
ARCHIVE_DIRNAME = "_archive"


def _utc_now() -> datetime:
    return datetime.now(UTC)


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


def _idle_days(skill: dict[str, Any], now: datetime) -> int | None:
    last = _parse_iso(skill.get("last_used")) or _parse_iso(skill.get("created_at"))
    if last is None:
        return None
    return max(0, int((now - last).total_seconds() // 86400))


def is_curatable(skill: dict[str, Any]) -> bool:
    name = str(skill.get("name") or "")
    if is_protected_skill(skill, name):
        return False
    if skill.get("pinned") is True:
        return False
    origin = str(skill.get("origin") or "").strip().lower()
    return origin in {"agent", "learn"}


def _rewrite(skill: dict[str, Any], **updates: Any) -> None:
    filepath = Path(str(skill.get("filepath") or ""))
    if not filepath.is_file():
        return
    meta = {
        k: v
        for k, v in skill.items()
        if k not in {"content", "filepath", "_source", "relevance_distance"}
    }
    meta.update(updates)
    body = skill.get("content") or ""
    filepath.write_text(
        "---\n" + yaml.dump(meta, default_flow_style=False) + "---\n\n" + body,
        encoding="utf-8",
    )
    skill.update(updates)


class SkillCurator:
    """active → stale → ``_archive/<date>/``. Bundled/hub/pinned are skipped."""

    def __init__(
        self,
        manager: Any,
        *,
        stale_after_days: int = STALE_AFTER_DAYS,
        archive_after_days: int = ARCHIVE_AFTER_DAYS,
    ):
        self.manager = manager
        self.skills_dir = Path(manager.skills_dir)
        self.stale_after_days = max(1, int(stale_after_days))
        self.archive_after_days = max(self.stale_after_days, int(archive_after_days))

    def _ensure_loaded(self) -> None:
        if not self.manager.all_skills:
            self.manager.load_all_skills(defer_index=True)

    def inspect(self) -> list[dict[str, Any]]:
        self._ensure_loaded()
        now = _utc_now()
        rows: list[dict[str, Any]] = []
        for name, skill in sorted(self.manager.all_skills.items()):
            idle = _idle_days(skill, now)
            curatable = is_curatable(skill)
            state = str(skill.get("state") or "active")
            action = "keep"
            if curatable and idle is not None:
                if idle >= self.archive_after_days:
                    action = "archive"
                elif idle >= self.stale_after_days:
                    action = "stale"
            rows.append(
                {
                    "name": name,
                    "origin": skill.get("origin") or skill.get("_source") or "",
                    "state": state,
                    "idle_days": idle,
                    "use_count": int(skill.get("use_count") or 0),
                    "pinned": bool(skill.get("pinned")),
                    "curatable": curatable,
                    "action": action if curatable else "skip",
                }
            )
        return rows

    def status(self) -> dict[str, Any]:
        rows = self.inspect()
        return {
            "stale_after_days": self.stale_after_days,
            "archive_after_days": self.archive_after_days,
            "total": len(rows),
            "curatable": sum(1 for r in rows if r["curatable"]),
            "would_stale": [r["name"] for r in rows if r["action"] == "stale"],
            "would_archive": [r["name"] for r in rows if r["action"] == "archive"],
            "pinned": [r["name"] for r in rows if r["pinned"]],
            "skills": rows,
            "archived": self.list_archived(),
        }

    def list_archived(self) -> list[dict[str, str]]:
        root = self.skills_dir / ARCHIVE_DIRNAME
        if not root.is_dir():
            return []
        found: list[dict[str, str]] = []
        for path in sorted(root.rglob("*.md")):
            found.append(
                {
                    "name": path.stem,
                    "path": str(path.relative_to(self.skills_dir)),
                }
            )
        return found

    def run(self, *, dry_run: bool = True) -> dict[str, Any]:
        rows = self.inspect()
        stale_names = [r["name"] for r in rows if r["action"] == "stale"]
        archive_names = [r["name"] for r in rows if r["action"] == "archive"]
        report: dict[str, Any] = {
            "dry_run": dry_run,
            "stale": stale_names,
            "archived": [],
            "skipped": [r["name"] for r in rows if r["action"] == "skip"],
        }
        if dry_run:
            report["archived"] = archive_names
            return report
        for name in stale_names:
            skill = self.manager.all_skills.get(name)
            if skill:
                _rewrite(skill, state="stale")
        moved: list[str] = []
        day = _utc_now().strftime("%Y-%m-%d")
        dest_root = self.skills_dir / ARCHIVE_DIRNAME / day
        for name in archive_names:
            if self._archive_one(name, dest_root):
                moved.append(name)
        report["archived"] = moved
        if moved:
            try:
                from core.achievements.engine import AchievementStore

                AchievementStore(self.skills_dir).bump(
                    "skills_archived",
                    len(moved),
                    evidence={"names": moved[:12]},
                )
            except Exception:
                pass
        return report

    def _archive_one(self, name: str, dest_root: Path) -> bool:
        skill = self.manager.all_skills.get(name)
        if not skill:
            return False
        src = Path(str(skill.get("filepath") or ""))
        if not src.is_file():
            return False
        dest_root.mkdir(parents=True, exist_ok=True)
        dest = dest_root / src.name
        if dest.exists():
            dest = dest_root / f"{src.stem}-{_utc_now().strftime('%H%M%S')}{src.suffix}"
        shutil.move(str(src), str(dest))
        self.manager.all_skills.pop(name, None)
        return True

    def restore(self, name: str) -> Path:
        matches = [
            self.skills_dir / row["path"] for row in self.list_archived() if row["name"] == name
        ]
        if not matches:
            raise FileNotFoundError(name)
        src = matches[-1]
        dest = self.skills_dir / src.name
        if dest.exists():
            raise ValueError(f"live skill {name!r} already exists")
        shutil.move(str(src), str(dest))
        self.manager.load_all_skills(defer_index=True)
        skill = self.manager.all_skills.get(name)
        if skill:
            _rewrite(skill, state="active")
        return dest

    def pin(self, name: str, pinned: bool = True) -> None:
        self._ensure_loaded()
        skill = self.manager.all_skills.get(name)
        if not skill:
            raise FileNotFoundError(name)
        _rewrite(skill, pinned=bool(pinned))
