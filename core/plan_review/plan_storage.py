"""
Plan Storage — save and load execution plans to .helix/plan/.

Plans are saved as both Markdown (human-readable) and JSON (machine-readable)
after the user confirms them. This allows for plan history, resumption,
and analytics.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config_utils import get_local_plan_dir
from core.di.runtime_config import HelixRuntimeConfig

logger = logging.getLogger(__name__)

_PLAN_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*\.json$")

# Default (CWD/.helix/plan) — can be overridden by get_plan_dir(config)
PLAN_DIR = Path(".helix/plan")

# Test hook: tests can set _TEST_PLAN_DIR to a temp Path
_TEST_PLAN_DIR: Optional[Path] = None


def get_plan_dir(config: Optional[HelixRuntimeConfig] = None) -> Path:
    """Resolve the plan storage dir.

    Prefers local project .helix/plan (already the convention). If runtime config
    provides local_project_dir we respect it, else fall back to CWD.
    """
    if _TEST_PLAN_DIR is not None:
        _TEST_PLAN_DIR.mkdir(parents=True, exist_ok=True)
        return _TEST_PLAN_DIR
    if config and getattr(config, "local_project_dir", None):
        base = Path(config.local_project_dir)
        if not base.is_absolute():
            base = Path.cwd() / base
        d = base / "plan"
        d.mkdir(parents=True, exist_ok=True)
        return d
    # default behavior (CWD)
    d = get_local_plan_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


class InvalidPlanIdError(ValueError):
    """Raised when a plan id is malformed or escapes the plan directory."""


def resolve_plan_path(plan_dir: Path, plan_id: str) -> Path:
    """Resolve a plan filename within plan_dir; reject path traversal."""
    name = plan_id.strip()
    if not name or not _PLAN_ID_RE.fullmatch(name):
        raise InvalidPlanIdError(f"Invalid plan id: {plan_id!r}")

    root = plan_dir.resolve()
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root):
        raise InvalidPlanIdError(f"Invalid plan id: {plan_id!r}")
    return candidate


def save_plan(
    plan_steps: List[Dict[str, Any]],
    conversation_id: str = "default",
    metadata: Optional[Dict[str, Any]] = None,
    plan_status: str = "confirmed",
    analysis: Optional[Dict[str, Any]] = None,
    architecture: Optional[Dict[str, Any]] = None,
) -> Path:
    """Save a plan to .helix/plan/ as both .md and .json.

    Args:
        plan_steps: List of plan step dicts.
        conversation_id: Conversation identifier.
        metadata: Additional metadata.
        plan_status: Status string ("confirmed", "auto_execute", etc.).
        analysis: Task analysis dict (task_summary, complexity, etc.).
        architecture: Architecture dict (approach, tech_stack, risks, etc.).

    Returns:
        Path to the saved .md file.
    """
    plan_dir = get_plan_dir()
    plan_dir.mkdir(parents=True, exist_ok=True)

    # Enrich metadata with analysis and architecture
    enriched_metadata = dict(metadata or {})
    if analysis:
        enriched_metadata["analysis"] = analysis
    if architecture:
        enriched_metadata["architecture"] = architecture

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Sanitize conversation_id for use as filename
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in conversation_id[:8])
    base_name = f"{timestamp}_{safe_id}"

    # Save Markdown version
    plan_dir = get_plan_dir()
    md_path = plan_dir / f"{base_name}.md"
    md_content = _format_plan_markdown(plan_steps, conversation_id, enriched_metadata, plan_status)
    md_path.write_text(md_content, encoding="utf-8")

    # Save JSON version
    json_path = plan_dir / f"{base_name}.json"
    json_data = {
        "conversation_id": conversation_id,
        "timestamp": timestamp,
        "status": plan_status,
        "steps": plan_steps,
        "metadata": metadata or {},
    }
    json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info(f"Plan saved to {md_path} ({len(plan_steps)} steps, status={plan_status})")
    return md_path


def load_plan(path: str) -> Dict[str, Any]:
    """Load a plan from a JSON file.

    Args:
        path: Path to the .json plan file (or .md — will look for .json counterpart).

    Returns:
        Dict with conversation_id, timestamp, status, steps, metadata.
    """
    plan_path = Path(path)

    # If .md given, look for .json counterpart
    if plan_path.suffix == ".md":
        plan_path = plan_path.with_suffix(".json")

    if not plan_path.exists():
        raise FileNotFoundError(f"Plan file not found: {plan_path}")

    return json.loads(plan_path.read_text(encoding="utf-8"))


def list_plans(limit: int = 20) -> List[Dict[str, Any]]:
    """List all saved plans, newest first.

    Args:
        limit: Maximum number of plans to return.

    Returns:
        List of dicts with path, timestamp, status, step_count.
    """
    plan_dir = get_plan_dir()
    if not plan_dir.exists():
        return []

    plans = []
    for json_file in sorted(plan_dir.glob("*.json"), reverse=True)[:limit]:
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            plans.append({
                "path": str(json_file),
                "timestamp": data.get("timestamp", ""),
                "status": data.get("status", ""),
                "step_count": len(data.get("steps", [])),
                "conversation_id": data.get("conversation_id", ""),
            })
        except Exception:
            continue

    return plans


def update_plan_progress(path: str, completed_steps: List[int]) -> None:
    """Update the progress of a plan.

    Args:
        path: Path to the .json plan file.
        completed_steps: List of step indices that are done.
    """
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
    plan_steps: List[Dict[str, Any]],
    conversation_id: str,
    metadata: Optional[Dict[str, Any]],
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
            lines.append(f"**{k}**: {v}")
        lines.append("")

    # Analysis section
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

    # Architecture section
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

    # Steps section
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