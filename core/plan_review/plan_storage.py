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
from core.paths import realpath_under
from core.di.runtime_config import HolixRuntimeConfig

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
    """Resolve the plan storage dir under the current project (.holix/plans/)."""
    if _TEST_PLAN_DIR is not None:
        _TEST_PLAN_DIR.mkdir(parents=True, exist_ok=True)
        return _TEST_PLAN_DIR
    if config and getattr(config, "local_project_dir", None):
        base = Path(config.local_project_dir)
        if not base.is_absolute():
            base = Path.cwd() / base
        d = base / _PLANS_SUBDIR
    else:
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
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in conversation_id[:8])
    base_name = f"{timestamp}_{safe_id}"

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
        "plan_id": plan_id,
        "conversation_id": conversation_id,
        "timestamp": timestamp,
        "status": plan_status,
        "user_input": user_input,
        "steps": plan_steps,
        "analysis": analysis,
        "architecture": architecture,
        "plan_report": plan_report,
        "plan_reasoning": plan_reasoning,
        "metadata": metadata or {},
        "markdown_path": str(md_path),
    }
    json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info(
        f"Plan saved to {md_path} ({len(plan_steps)} steps, status={plan_status})"
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


def list_plans(
    limit: int = 20,
    config: HolixRuntimeConfig | None = None,
) -> list[dict[str, Any]]:
    """List saved plans from `.holix/plans/` (and legacy `.holix/plan/`), newest first."""
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
                plans.append({
                    "path": str(json_file),
                    "timestamp": data.get("timestamp", ""),
                    "status": data.get("status", ""),
                    "step_count": len(data.get("steps", [])),
                    "conversation_id": data.get("conversation_id", ""),
                    "plan_id": data.get("plan_id", ""),
                    "title": summary,
                    "user_input": (data.get("user_input") or "")[:200],
                })
            except Exception:
                continue

    plans.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return plans[:limit]


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

        lines.append(f"### [⬜] Step {num}: {desc}")
        if tools:
            lines.append(f"- **Tools**: {', '.join(tools)}")
        if expected:
            lines.append(f"- **Expected**: {expected}")
        if criteria:
            lines.append(f"- **Success Criteria**: {criteria}")
        if parallel is not None:
            lines.append(f"- **Parallel Group**: {parallel}")
        lines.append("")

    return "\n".join(lines)