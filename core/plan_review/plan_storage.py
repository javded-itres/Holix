"""
Plan Storage — save and load execution plans to .holix/plans/.

Plans are saved as both Markdown (human-readable) and JSON (machine-readable)
after the user confirms them. This allows for plan history, resumption,
and analytics.
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config_utils import get_local_plan_dir
from core.di.runtime_config import HolixRuntimeConfig
from core.paths import realpath_under

logger = logging.getLogger(__name__)

_PLAN_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*\.json$")
_LEGACY_PLAN_SUBDIR = "plan"
_PLANS_SUBDIR = "plans"

# Default (CWD/.holix/plans) — can be overridden by get_plan_dir(config)
PLAN_DIR = Path(".holix") / _PLANS_SUBDIR

# Test hook: tests can set _TEST_PLAN_DIR to a temp Path
_TEST_PLAN_DIR: Path | None = None


def get_plan_dir(
    config: HolixRuntimeConfig | None = None,
    *,
    cwd: str | None = None,
) -> Path:
    """Resolve the plan storage dir under the current project (.holix/plans/).

    Prefer the agent workspace root (Studio per-user workspace) so plans are
    stored next to the project the user is editing — not under Studio install CWD.
    """
    if _TEST_PLAN_DIR is not None:
        _TEST_PLAN_DIR.mkdir(parents=True, exist_ok=True)
        return _TEST_PLAN_DIR
    if config is not None:
        workspace_root = getattr(config, "workspace_root", None)
        if workspace_root:
            base = Path(str(workspace_root)).expanduser()
            if not base.is_absolute():
                base = Path.cwd() / base
            d = base.resolve() / ".holix" / _PLANS_SUBDIR
            d.mkdir(parents=True, exist_ok=True)
            return d
        local = getattr(config, "local_project_dir", None)
        # Ignore the bare default ".holix" — that relative path lands in process CWD
        # (Studio install tree) and hides plans from the user's project.
        if local and str(local).strip() not in {"", ".holix", ".holix/"}:
            base = Path(str(local)).expanduser()
            if not base.is_absolute():
                base = Path.cwd() / base
            # local_project_dir may already be ".../.holix" or a plans parent
            base_resolved = base.resolve()
            if base_resolved.name == "plans":
                d = base_resolved
            elif base_resolved.name == ".holix":
                d = base_resolved / _PLANS_SUBDIR
            else:
                d = base_resolved / ".holix" / _PLANS_SUBDIR
            d.mkdir(parents=True, exist_ok=True)
            return d
    d = get_local_plan_dir(cwd)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _legacy_plan_dir(
    config: HolixRuntimeConfig | None = None,
    *,
    cwd: str | None = None,
) -> Path:
    primary = get_plan_dir(config, cwd=cwd)
    return primary.parent / _LEGACY_PLAN_SUBDIR


def _plan_search_dirs(
    config: HolixRuntimeConfig | None = None,
    *,
    cwd: str | None = None,
) -> list[Path]:
    """Primary `.holix/plans/` first, then legacy `.holix/plan/` if present."""
    dirs = [get_plan_dir(config, cwd=cwd)]
    legacy = _legacy_plan_dir(config, cwd=cwd)
    if legacy.is_dir() and legacy not in dirs:
        dirs.append(legacy)
    return dirs


class InvalidPlanIdError(ValueError):
    """Raised when a plan id is malformed or escapes the plan directory."""


def resolve_plan_path(plan_dir: Path, plan_id: str) -> Path:
    """Resolve a plan filename within plan_dir; reject path traversal."""
    name = plan_id.strip()
    if not name or not _PLAN_ID_RE.fullmatch(name):
        raise InvalidPlanIdError(f"Invalid plan id: {plan_id!r}")

    try:
        return realpath_under(plan_dir.resolve(), name)
    except ValueError as exc:
        raise InvalidPlanIdError(f"Invalid plan id: {plan_id!r}") from exc


def save_plan(
    plan_steps: list[dict[str, Any]],
    conversation_id: str = "default",
    metadata: dict[str, Any] | None = None,
    plan_status: str = "confirmed",
    analysis: dict[str, Any] | None = None,
    architecture: dict[str, Any] | None = None,
    plan_report: dict[str, Any] | None = None,
    plan_reasoning: str = "",
    user_input: str = "",
    plan_id: str = "",
    rendered_markdown: str = "",
    config: HolixRuntimeConfig | None = None,
) -> Path:
    """Save a confirmed plan to .holix/plans/ as both .md and .json."""
    plan_dir = get_plan_dir(config)
    plan_dir.mkdir(parents=True, exist_ok=True)

    enriched_metadata = dict(metadata or {})
    if analysis:
        enriched_metadata["analysis"] = analysis
    if architecture:
        enriched_metadata["architecture"] = architecture
    if plan_report:
        enriched_metadata["plan_report"] = plan_report
    if plan_reasoning:
        enriched_metadata["plan_reasoning"] = plan_reasoning
    if user_input:
        enriched_metadata["user_input"] = user_input
    if plan_id:
        enriched_metadata["plan_id"] = plan_id

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_cid = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in (conversation_id or "studio")[:12]
    )
    # Always mint a stable plan_id — timestamp-only names create orphan files
    # when draft (with id) and confirm (without id) both save.
    raw_pid = (plan_id or "").strip()
    if not raw_pid:
        import uuid

        raw_pid = f"plan_{uuid.uuid4().hex[:10]}"
        logger.info("save_plan: empty plan_id — minted %s", raw_pid)
    plan_id = raw_pid
    safe_pid = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in plan_id[:24]
    )
    # Stable name so draft → confirm → progress all overwrite one pair.
    base_name = f"{safe_pid}_{safe_cid}" if safe_cid else safe_pid

    if rendered_markdown.strip():
        md_content = rendered_markdown.strip() + "\n"
    else:
        try:
            from core.plan_review.markdown_builder import build_plan_markdown

            md_content = build_plan_markdown(
                plan_steps=plan_steps,
                step_count=len(plan_steps),
                reasoning=plan_reasoning,
                user_input=user_input,
                analysis=analysis,
                architecture=architecture,
                plan_report=plan_report,
            )
        except Exception:
            md_content = _format_plan_markdown(
                plan_steps, conversation_id, enriched_metadata, plan_status
            )

    md_path = plan_dir / f"{base_name}.md"
    md_path.write_text(md_content, encoding="utf-8")

    json_path = plan_dir / f"{base_name}.json"
    json_data = {
        "plan_id": plan_id or base_name,
        "conversation_id": conversation_id,
        "timestamp": timestamp,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "status": plan_status,
        "user_input": user_input,
        "steps": plan_steps,
        "analysis": analysis,
        "architecture": architecture,
        "plan_report": plan_report,
        "plan_reasoning": plan_reasoning,
        "metadata": metadata or {},
        "markdown_path": str(md_path),
        "json_path": str(json_path),
    }
    json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info(
        "Plan saved to %s (%s steps, status=%s)",
        json_path,
        len(plan_steps),
        plan_status,
    )
    return md_path


def resolve_trusted_plan_file(
    path: str | Path,
    config: HolixRuntimeConfig | None = None,
) -> Path:
    """Resolve a plan file and ensure it stays under project plan directories."""
    text = str(path).strip()
    if not text or "\0" in text:
        raise InvalidPlanIdError(f"Invalid plan path: {path!r}")
    normalized = text.replace("\\", "/")
    if normalized.startswith("../") or "/../" in f"/{normalized}/":
        raise InvalidPlanIdError(f"Plan path outside plan directories: {path}")
    expanded = os.path.expanduser(text)
    resolved = Path(os.path.realpath(expanded))
    if resolved.suffix == ".md":
        resolved = resolved.with_suffix(".json")
    allowed_roots = [Path(os.path.realpath(str(d.resolve()))) for d in _plan_search_dirs(config)]
    if not any(
        resolved == root or resolved.is_relative_to(root)
        for root in allowed_roots
    ):
        raise InvalidPlanIdError(f"Plan path outside plan directories: {path}")
    return resolved


def load_plan(
    path: str,
    config: HolixRuntimeConfig | None = None,
) -> dict[str, Any]:
    """Load a plan from a JSON file under `.holix/plans/` (or legacy `.holix/plan/`)."""
    plan_path = resolve_trusted_plan_file(path, config)

    if not plan_path.exists():
        raise FileNotFoundError(f"Plan file not found: {plan_path}")

    return json.loads(plan_path.read_text(encoding="utf-8"))


def delete_plan(
    path: str,
    config: HolixRuntimeConfig | None = None,
) -> dict[str, Any]:
    """Delete a plan JSON and its companion Markdown (if present).

    ``path`` must resolve under project plan directories (same trust rules as load).
    """
    plan_path = resolve_trusted_plan_file(path, config)
    if not plan_path.exists():
        raise FileNotFoundError(f"Plan file not found: {plan_path}")

    plan_id = ""
    md_path = plan_path.with_suffix(".md")
    try:
        data = json.loads(plan_path.read_text(encoding="utf-8"))
        plan_id = str(data.get("plan_id") or "")
        md_hint = str(data.get("markdown_path") or "").strip()
        if md_hint:
            candidate = Path(os.path.realpath(os.path.expanduser(md_hint)))
            allowed = [
                Path(os.path.realpath(str(d.resolve())))
                for d in _plan_search_dirs(config)
            ]
            if candidate.suffix.lower() == ".md" and any(
                candidate == root or candidate.is_relative_to(root) for root in allowed
            ):
                md_path = candidate
    except Exception:
        pass

    removed: list[str] = []
    for p in (plan_path, md_path):
        try:
            if p.exists() and p.is_file():
                p.unlink()
                removed.append(str(p))
        except OSError as exc:
            logger.warning("Failed to delete plan file %s: %s", p, exc)

    if not removed:
        raise FileNotFoundError(f"No plan files removed for: {path}")

    logger.info("Deleted plan files: %s", removed)
    return {
        "ok": True,
        "removed": removed,
        "path": str(plan_path),
        "plan_id": plan_id,
    }


def apply_step_status(
    plan_steps: list[dict[str, Any]],
    *,
    done_step: int | None = None,
    in_progress_step: int | None = None,
    mark_all_done: bool = False,
) -> list[dict[str, Any]]:
    """Return a copy of plan_steps with checkbox statuses updated."""
    from core.plan_review.parser import normalize_step_status

    out: list[dict[str, Any]] = []
    for i, raw in enumerate(plan_steps or []):
        step = dict(raw) if isinstance(raw, dict) else {"description": str(raw)}
        num = int(step.get("step") or (i + 1))
        cur = normalize_step_status(step.get("status"))
        if mark_all_done:
            cur = "done"
        elif done_step is not None and num == int(done_step):
            cur = "done"
        elif in_progress_step is not None and num == int(in_progress_step):
            if cur != "done":
                cur = "in_progress"
        elif (
            in_progress_step is not None
            and num != int(in_progress_step)
            and cur == "in_progress"
        ):
            # Only one active step at a time
            cur = "pending" if done_step is None or num > int(done_step or 0) else cur
        step["status"] = cur
        step["step"] = num
        out.append(step)
    # When advancing: any step number < in_progress and not done → done (safety)
    if in_progress_step is not None:
        ip = int(in_progress_step)
        for step in out:
            num = int(step.get("step") or 0)
            if num < ip and step.get("status") != "done":
                step["status"] = "done"
    if done_step is not None:
        ds = int(done_step)
        for step in out:
            num = int(step.get("step") or 0)
            if num <= ds:
                step["status"] = "done"
    return out


def persist_plan_steps_progress(
    plan_id: str,
    plan_steps: list[dict[str, Any]],
    *,
    conversation_id: str = "",
    plan_status: str | None = None,
    config: HolixRuntimeConfig | None = None,
) -> str | None:
    """Update steps (checkbox progress) on the saved plan file for plan_id."""
    pid = (plan_id or "").strip()
    if not pid or not plan_steps:
        return None
    entries = list_plans(limit=80, config=config)
    match = None
    for e in entries:
        if str(e.get("plan_id") or "") == pid:
            match = e
            break
        path = str(e.get("path") or "")
        if pid and pid in path:
            match = e
            break
    if not match:
        # Still save a fresh progress snapshot
        try:
            path = save_plan(
                plan_steps,
                conversation_id or "studio",
                plan_status=plan_status or "in_progress",
                plan_id=pid,
                config=config,
            )
            return str(path.with_suffix(".json"))
        except Exception:
            logger.warning("persist_plan_steps_progress: save failed", exc_info=True)
            return None
    try:
        data = load_plan(match["path"], config=config)
        data["steps"] = plan_steps
        if plan_status:
            data["status"] = plan_status
        md = str(data.get("markdown_path") or "")
        path = save_plan(
            plan_steps,
            data.get("conversation_id") or conversation_id or "studio",
            metadata=data.get("metadata") or {},
            plan_status=plan_status or data.get("status") or "in_progress",
            analysis=data.get("analysis"),
            architecture=data.get("architecture"),
            plan_report=data.get("plan_report"),
            plan_reasoning=data.get("plan_reasoning") or "",
            user_input=data.get("user_input") or "",
            plan_id=pid,
            rendered_markdown="",  # rebuild from steps so checkboxes refresh
            config=config,
        )
        return str(path.with_suffix(".json"))
    except Exception:
        logger.warning("persist_plan_steps_progress failed for %s", pid, exc_info=True)
        return None


def list_plans(
    limit: int = 20,
    config: HolixRuntimeConfig | None = None,
) -> list[dict[str, Any]]:
    """List saved plans from `.holix/plans/` (and legacy `.holix/plan/`), newest first.

    Dedupes by ``plan_id`` (keeps newest). For the same conversation, prefers
    confirmed/in_progress over pending_review drafts when timestamps are close.
    """
    plans: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    for plan_dir in _plan_search_dirs(config):
        if not plan_dir.exists():
            continue
        for json_file in sorted(plan_dir.glob("*.json"), reverse=True):
            path_key = str(json_file.resolve())
            if path_key in seen_paths:
                continue
            seen_paths.add(path_key)
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                summary = _plan_summary_from_data(data)
                steps = data.get("steps") or []
                done_count = sum(
                    1
                    for s in steps
                    if isinstance(s, dict)
                    and str(s.get("status") or "").lower()
                    in ("done", "completed", "complete", "finished")
                )
                plans.append({
                    "path": str(json_file),
                    "timestamp": data.get("timestamp", ""),
                    "updated_at": data.get("updated_at", "") or data.get("timestamp", ""),
                    "status": data.get("status", ""),
                    "step_count": len(steps),
                    "steps_done": done_count,
                    "conversation_id": data.get("conversation_id", ""),
                    "plan_id": data.get("plan_id", "") or json_file.stem,
                    "title": summary,
                    "user_input": (data.get("user_input") or "")[:200],
                })
            except Exception:
                continue

    status_rank = {
        "completed": 0,
        "confirmed": 1,
        "auto_execute": 1,
        "in_progress": 2,
        "pending_review": 3,
        "draft": 4,
    }

    def _sort_key(item: dict[str, Any]) -> tuple:
        # Better status first, then newest
        rank = status_rank.get(str(item.get("status") or "").lower(), 9)
        ts = str(item.get("updated_at") or item.get("timestamp") or "")
        return (rank, ts)

    # Prefer better status; within same status, prefer newer timestamps.
    plans.sort(key=_sort_key)
    # Stable secondary: reverse timestamp among equal ranks
    plans.sort(
        key=lambda item: str(item.get("updated_at") or item.get("timestamp") or ""),
        reverse=True,
    )
    plans.sort(
        key=lambda item: status_rank.get(str(item.get("status") or "").lower(), 9)
    )

    # 1) Unique plan_id (first = best after sort)
    by_id: dict[str, dict[str, Any]] = {}
    for p in plans:
        pid = str(p.get("plan_id") or p.get("path") or "")
        if pid not in by_id:
            by_id[pid] = p

    # 2) Collapse same conversation + same task (orphans from lost plan_id)
    winners: list[dict[str, Any]] = []
    seen_task: set[str] = set()
    for p in by_id.values():
        cid = str(p.get("conversation_id") or "")
        task = " ".join(str(p.get("user_input") or "").lower().split())[:120]
        key = f"{cid}::{task}" if (cid or task) else str(p.get("plan_id") or p.get("path"))
        if key in seen_task:
            continue
        seen_task.add(key)
        winners.append(p)

    winners.sort(
        key=lambda item: str(item.get("updated_at") or item.get("timestamp") or ""),
        reverse=True,
    )
    return winners[:limit]


def load_latest_plan(
    config: HolixRuntimeConfig | None = None,
) -> dict[str, Any] | None:
    """Load the most recent saved plan from the project plans directory."""
    entries = list_plans(limit=1, config=config)
    if not entries:
        return None
    try:
        return load_plan(entries[0]["path"])
    except Exception as exc:
        logger.warning(f"Failed to load latest plan: {exc}")
        return None


def format_saved_plans_context(
    config: HolixRuntimeConfig | None = None,
    *,
    limit: int = 5,
) -> str:
    """Summarize saved project plans for plan_node / agent prompts."""
    plan_dir = get_plan_dir(config)
    entries = list_plans(limit=limit, config=config)
    if not entries:
        return (
            f"No saved plans in `{plan_dir}` yet. "
            "Confirmed plans are stored there after user approval."
        )

    lines = [
        f"Saved plans directory: `{plan_dir}`",
        "When the user refers to an existing plan, load it from this directory "
        "(newest JSON + matching Markdown). Prefer updating an approved plan "
        "over creating a duplicate unless the task changed significantly.",
        "",
    ]
    for entry in entries:
        title = entry.get("title") or entry.get("user_input") or "Untitled plan"
        lines.append(
            f"- `{Path(entry['path']).name}` — {title} "
            f"({entry.get('step_count', 0)} steps, status={entry.get('status', '?')}, "
            f"ts={entry.get('timestamp', '?')})"
        )
    return "\n".join(lines)


def _plan_summary_from_data(data: dict[str, Any]) -> str:
    report = data.get("plan_report") or {}
    if isinstance(report, dict) and report.get("title"):
        return str(report["title"])
    analysis = data.get("analysis") or {}
    if isinstance(analysis, dict) and analysis.get("task_summary"):
        return str(analysis["task_summary"])
    user_input = data.get("user_input") or ""
    if user_input:
        return user_input[:120]
    steps = data.get("steps") or []
    if steps and isinstance(steps[0], dict):
        return str(steps[0].get("description", ""))[:120]
    return "Saved plan"


def update_plan_progress(path: str, completed_steps: list[int]) -> None:
    """Update the progress of a plan."""
    plan_path = Path(path)
    if plan_path.suffix == ".md":
        plan_path = plan_path.with_suffix(".json")

    if not plan_path.exists():
        logger.warning(f"Plan file not found for progress update: {plan_path}")
        return

    data = json.loads(plan_path.read_text(encoding="utf-8"))
    data["completed_steps"] = completed_steps
    data["updated_at"] = datetime.now().isoformat()

    plan_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _format_plan_markdown(
    plan_steps: list[dict[str, Any]],
    conversation_id: str,
    metadata: dict[str, Any] | None,
    plan_status: str,
) -> str:
    """Format plan steps as a human-readable Markdown document."""
    lines = [
        f"# Plan — {conversation_id}",
        "",
        f"Created: {datetime.now().isoformat()}",
        f"Status: {plan_status}",
        f"Steps: {len(plan_steps)}",
        "",
    ]

    if metadata:
        for k, v in metadata.items():
            if k in {"analysis", "architecture", "plan_report"}:
                continue
            lines.append(f"**{k}**: {v}")
        lines.append("")

    analysis = metadata.get("analysis") if metadata else None
    if analysis:
        lines.append("## Analysis")
        lines.append("")
        lines.append(f"**Summary**: {analysis.get('task_summary', 'N/A')}")
        lines.append(f"**Complexity**: {analysis.get('complexity', 'N/A')}")
        questions = analysis.get("clarifying_questions", [])
        if questions:
            lines.append("**Questions**:")
            for q in questions:
                lines.append(f"- {q}")
        constraints = analysis.get("constraints", [])
        if constraints:
            lines.append("**Constraints**:")
            for c in constraints:
                lines.append(f"- {c}")
        lines.append("")

    architecture = metadata.get("architecture") if metadata else None
    if architecture:
        lines.append("## Architecture")
        lines.append("")
        lines.append(f"**Approach**: {architecture.get('approach', 'N/A')}")
        tech_stack = architecture.get("tech_stack", [])
        if tech_stack:
            lines.append(f"**Tech Stack**: {', '.join(tech_stack)}")
        lines.append(f"**Structure**: {architecture.get('structure', 'N/A')}")
        risks = architecture.get("risks", [])
        if risks:
            lines.append("")
            lines.append("### Risks")
            for r in risks:
                if isinstance(r, dict):
                    lines.append(f"- **{r.get('risk', 'N/A')}**: {r.get('mitigation', 'N/A')}")
                else:
                    lines.append(f"- {r}")
        lines.append("")

    lines.append("## Steps")
    lines.append("")

    for step in plan_steps:
        num = step.get("step", "?")
        desc = step.get("description", "")
        tools = step.get("tools_needed", [])
        expected = step.get("expected_output", "")
        criteria = step.get("success_criteria", "")
        parallel = step.get("parallel_group")
        status = str(step.get("status") or "pending").strip().lower()
        box = "[x]" if status in ("done", "completed", "complete", "finished") else "[ ]"
        label = ""
        if status in ("in_progress", "active", "running", "current"):
            label = "*in progress* "
        elif status in ("failed", "error", "blocked"):
            label = "*failed* "

        # GFM task list: empty at create, checked when done.
        lines.append(f"- {box} {label}**Step {num}:** {desc}")
        if tools:
            lines.append(f"  - **Tools**: {', '.join(tools)}")
        if expected:
            lines.append(f"  - **Expected**: {expected}")
        if criteria:
            lines.append(f"  - **Success Criteria**: {criteria}")
        if parallel is not None:
            lines.append(f"  - **Parallel Group**: {parallel}")
        lines.append("")

    return "\n".join(lines)