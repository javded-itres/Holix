"""Stage auto-created skills for human review instead of writing them live."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PENDING_DIRNAME = "_pending"
MAX_PENDING = 30
TTL_DAYS = 14
_ACTIONS = frozenset({"create", "patch", "reuse"})


def pending_root(skills_dir: Path | str) -> Path:
    return Path(skills_dir) / PENDING_DIRNAME


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


def new_proposal_id(now: datetime | None = None) -> str:
    stamp = (now or _utc_now()).strftime("%Y%m%d")
    return f"psp-{stamp}-{secrets.token_hex(4)}"


def is_protected_skill(skill: dict[str, Any] | None, name: str) -> bool:
    """Bundled / hub skills must not be overwritten by auto-proposals."""
    slug = (name or "").strip()
    if not slug:
        return True
    try:
        from core.skills.bundled import bundled_skill_names

        if slug in set(bundled_skill_names()):
            return True
    except Exception:
        pass
    if not skill:
        return False
    origin = str(skill.get("origin") or "").strip().lower()
    if origin in {"bundled", "hub"}:
        return True
    path = str(skill.get("filepath") or "").replace("\\", "/")
    return "/_hub/" in path or path.endswith("/_hub")


def _note(skills_dir: Path | str, signal: str, **evidence: Any) -> list[dict[str, Any]]:
    try:
        from core.achievements.engine import record_skill_signal

        return record_skill_signal(skills_dir, signal, evidence=evidence or None)
    except Exception:
        return []


def _note_approved(
    skills_dir: Path | str,
    rec: dict[str, Any],
    assign_to: list[str] | None,
    *,
    patched: bool,
) -> list[dict[str, Any]]:
    newly: list[dict[str, Any]] = []
    ev = {"skill_name": rec.get("name"), "proposal_id": rec.get("id")}
    newly.extend(_note(skills_dir, "approved", **ev))
    if patched:
        newly.extend(_note(skills_dir, "patched", **ev))
    if rec.get("origin") == "learn":
        newly.extend(_note(skills_dir, "learned_approved", **ev))
    slots = {s.strip() for s in (assign_to or []) if str(s).strip()}
    if "main" in slots:
        newly.extend(_note(skills_dir, "main_assigned", **ev))
    return newly


class SkillProposalStore:
    """Filesystem queue under ``<skills_dir>/_pending/<id>/``."""

    def __init__(self, skills_dir: Path | str):
        self.skills_dir = Path(skills_dir)
        self.root = pending_root(self.skills_dir)

    def _dir(self, proposal_id: str) -> Path:
        safe = Path(proposal_id).name
        if not safe.startswith("psp-") or "/" in proposal_id or "\\" in proposal_id:
            raise ValueError(f"invalid proposal id: {proposal_id!r}")
        return self.root / safe

    def _meta_path(self, proposal_id: str) -> Path:
        return self._dir(proposal_id) / "proposal.json"

    def _skill_path(self, proposal_id: str) -> Path:
        return self._dir(proposal_id) / "SKILL.md"

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _load(self, proposal_id: str) -> dict[str, Any] | None:
        path = self._meta_path(proposal_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        data["id"] = data.get("id") or proposal_id
        skill_md = self._skill_path(proposal_id)
        if skill_md.is_file() and not data.get("content"):
            data["content"] = skill_md.read_text(encoding="utf-8")
        return data

    def _save(self, rec: dict[str, Any]) -> dict[str, Any]:
        pid = str(rec["id"])
        content = str(rec.get("content") or "")
        meta = {k: v for k, v in rec.items() if k != "content"}
        self._write_json(self._meta_path(pid), meta)
        if content:
            self._skill_path(pid).write_text(content, encoding="utf-8")
        return rec

    def _drop(self, proposal_id: str) -> None:
        import shutil

        folder = self._dir(proposal_id)
        if folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)

    def expire_stale(self) -> list[str]:
        """Drop expired / overflow pending items. Returns removed ids."""
        removed: list[str] = []
        now = _utc_now()
        pending = self.list_pending(include_expired=True)
        for rec in pending:
            exp = _parse_iso(rec.get("expires_at"))
            if exp and exp < now:
                self._drop(str(rec["id"]))
                removed.append(str(rec["id"]))
        live = [r for r in self.list_pending() if r["id"] not in removed]
        live.sort(key=lambda r: str(r.get("created_at") or ""))
        while len(live) > MAX_PENDING:
            old = live.pop(0)
            self._drop(str(old["id"]))
            removed.append(str(old["id"]))
        return removed

    def list_pending(self, *, include_expired: bool = False) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        now = _utc_now()
        for child in sorted(self.root.iterdir()):
            if not child.is_dir() or not child.name.startswith("psp-"):
                continue
            rec = self._load(child.name)
            if not rec or rec.get("status") != "pending":
                continue
            exp = _parse_iso(rec.get("expires_at"))
            if exp and exp < now and not include_expired:
                continue
            rows.append(rec)
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return rows

    def get(self, proposal_id: str) -> dict[str, Any] | None:
        return self._load(proposal_id)

    def stage(
        self,
        *,
        name: str,
        action: str,
        content: str,
        description: str = "",
        tags: list[str] | None = None,
        examples: list[str] | None = None,
        target_name: str | None = None,
        origin: str = "session",
        source_session: str = "",
        source_run: str = "",
        agent_slot: str = "main",
        reason: str = "",
        duplicate_of: str | None = None,
        refuse_reason: str = "",
        quality_score: int = 0,
        locale: str = "",
    ) -> dict[str, Any]:
        from core.hub.normalize import slugify_skill_name

        action = (action or "create").strip().lower()
        if action not in _ACTIONS:
            raise ValueError(f"invalid proposal action: {action!r}")
        name = slugify_skill_name(name)
        if not name:
            raise ValueError("proposal needs a skill name")
        self.expire_stale()
        if len(self.list_pending()) >= MAX_PENDING:
            self.expire_stale()
        if len(self.list_pending()) >= MAX_PENDING:
            raise ValueError(f"pending skill queue is full ({MAX_PENDING})")
        now = _utc_now()
        pid = new_proposal_id(now)
        rec: dict[str, Any] = {
            "id": pid,
            "action": action,
            "status": "pending",
            "name": name,
            "target_name": slugify_skill_name(target_name or name),
            "origin": origin or "session",
            "source_session": source_session or "",
            "source_run": source_run or "",
            "agent_slot": agent_slot or "main",
            "reason": reason or "",
            "duplicate_of": duplicate_of,
            "refuse_reason": refuse_reason or "",
            "quality_score": int(quality_score or 0),
            "locale": locale or "",
            "auto_applied": False,
            "description": description or "",
            "tags": list(tags or []),
            "examples": list(examples or []),
            "created_at": _iso(now),
            "expires_at": _iso(now + timedelta(days=TTL_DAYS)),
            "content": content or "",
        }
        return self._save(rec)

    def reject(self, proposal_id: str, *, reason: str = "") -> dict[str, Any]:
        rec = self.get(proposal_id)
        if not rec:
            raise FileNotFoundError(proposal_id)
        if rec.get("status") != "pending":
            raise ValueError(f"proposal {proposal_id} is {rec.get('status')}")
        rec["status"] = "rejected"
        rec["resolved_at"] = _iso(_utc_now())
        rec["reject_reason"] = reason or ""
        rec["unlocks"] = _note(
            self.skills_dir,
            "refused",
            skill_name=rec.get("name"),
            proposal_id=proposal_id,
        )
        self._drop(proposal_id)
        return rec

    def approve(
        self,
        proposal_id: str,
        *,
        manager: Any,
        assign_to: list[str] | None = None,
    ) -> dict[str, Any]:
        rec = self.get(proposal_id)
        if not rec:
            raise FileNotFoundError(proposal_id)
        if rec.get("status") != "pending":
            raise ValueError(f"proposal {proposal_id} is {rec.get('status')}")
        action = rec.get("action") or "create"
        name = str(rec.get("target_name") or rec.get("name") or "")
        content = str(rec.get("content") or "")
        description = str(rec.get("description") or "")
        tags = list(rec.get("tags") or [])
        examples = list(rec.get("examples") or [])
        if not manager.all_skills:
            manager.load_all_skills(defer_index=True)

        if action == "reuse":
            rec["status"] = "merged"
            rec["merged_into"] = name
            rec["resolved_at"] = _iso(_utc_now())
            self._drop(proposal_id)
            return rec

        if action == "patch":
            existing = manager.all_skills.get(name)
            if is_protected_skill(existing, name):
                raise ValueError(f"cannot patch protected skill {name!r}")
            if not existing:
                action = "create"
            else:
                path = manager.patch_skill(
                    name,
                    description=description or None,
                    content=content or None,
                    tags=tags or None,
                )
                rec["status"] = "approved"
                rec["action"] = "patch"
                rec["filepath"] = str(path)
                rec["resolved_at"] = _iso(_utc_now())
                self._attach(manager, name, assign_to)
                rec["unlocks"] = _note_approved(self.skills_dir, rec, assign_to, patched=True)
                self._drop(proposal_id)
                return rec

        if is_protected_skill(manager.all_skills.get(name), name):
            raise ValueError(f"cannot overwrite protected skill {name!r}")
        path = manager.save_skill(
            name=name,
            description=description,
            content=content,
            tags=tags,
            examples=examples,
            assign=False,
            origin="learn" if rec.get("origin") == "learn" else "agent",
            source_session=str(rec.get("source_session") or ""),
            quality_score=int(rec.get("quality_score") or 0),
        )
        rec["status"] = "approved"
        rec["action"] = "create"
        rec["filepath"] = str(path)
        rec["resolved_at"] = _iso(_utc_now())
        self._attach(manager, name, assign_to)
        rec["unlocks"] = _note_approved(self.skills_dir, rec, assign_to, patched=False)
        self._drop(proposal_id)
        return rec

    def merge(
        self,
        proposal_id: str,
        target: str,
        *,
        manager: Any,
    ) -> dict[str, Any]:
        from core.hub.normalize import slugify_skill_name

        rec = self.get(proposal_id)
        if not rec:
            raise FileNotFoundError(proposal_id)
        if rec.get("status") != "pending":
            raise ValueError(f"proposal {proposal_id} is {rec.get('status')}")
        target_name = slugify_skill_name(target)
        if not manager.all_skills:
            manager.load_all_skills(defer_index=True)
        existing = manager.all_skills.get(target_name)
        if not existing:
            raise FileNotFoundError(target_name)
        if is_protected_skill(existing, target_name):
            raise ValueError(f"cannot merge into protected skill {target_name!r}")
        path = manager.patch_skill(
            target_name,
            description=str(rec.get("description") or "") or None,
            content=str(rec.get("content") or "") or None,
            tags=list(rec.get("tags") or []) or None,
        )
        rec["status"] = "merged"
        rec["merged_into"] = target_name
        rec["filepath"] = str(path)
        rec["resolved_at"] = _iso(_utc_now())
        rec["unlocks"] = _note_approved(self.skills_dir, rec, None, patched=True)
        self._drop(proposal_id)
        return rec

    @staticmethod
    def _attach(manager: Any, name: str, assign_to: list[str] | None) -> None:
        slots = [s.strip() for s in (assign_to or []) if str(s).strip()]
        for slot in slots:
            manager._attach_skill_to_agent(name, slot)
