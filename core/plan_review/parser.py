"""Plan response parsing (JSON, markdown-wrapped, plain-text fallbacks)."""

from __future__ import annotations

import json
import re
from typing import Any

PlanSteps = list[dict[str, Any]]
PlanAnalysis = dict[str, Any] | None
PlanArchitecture = dict[str, Any] | None
PlanReport = dict[str, Any] | None


def is_truncated_json(text: str) -> bool:
    """Heuristic: LLM hit max_tokens or was cut off before closing JSON."""
    cleaned = strip_markdown_code_blocks(text.strip())
    if not cleaned:
        return True
    if cleaned.count("{") != cleaned.count("}"):
        return True
    if cleaned.count("[") != cleaned.count("]"):
        return True
    tail = cleaned.rstrip()
    return not tail.endswith("}")


def is_development_report_complete(report: PlanReport) -> bool:
    """Check whether the BA-style approval report has the minimum required sections."""
    if not report:
        return False
    summary = report.get("summary") or {}
    if not str(summary.get("goal", "")).strip():
        return False
    if not report.get("development_stages"):
        return False
    priorities = report.get("priorities") or {}
    if not priorities.get("mvp"):
        return False
    if not report.get("dependencies"):
        return False
    if not report.get("blockers"):
        return False
    estimates = report.get("estimates") or {}
    if not estimates.get("stages") and estimates.get("total_hours") is None:
        return False
    return True


def parse_detailed_plan(
    text: str,
) -> tuple[PlanSteps, PlanAnalysis, PlanArchitecture, PlanReport, str]:
    """Parse LLM plan response into structured plan, analysis, architecture, and report."""
    text = text.strip()
    if not text:
        return [], None, None, None, ""

    try:
        data = json.loads(text)
        plan, analysis, architecture, report, reasoning = extract_plan_data(data)
        if plan:
            return plan, analysis, architecture, report, reasoning
    except json.JSONDecodeError:
        pass

    cleaned = strip_markdown_code_blocks(text)
    if cleaned != text:
        try:
            data = json.loads(cleaned)
            plan, analysis, architecture, report, reasoning = extract_plan_data(data)
            if plan:
                return plan, analysis, architecture, report, reasoning
        except json.JSONDecodeError:
            pass
        plan, analysis, architecture, report, reasoning = try_extract_json_from_text(cleaned)
        if plan:
            return plan, analysis, architecture, report, reasoning

    plan, analysis, architecture, report, reasoning = try_extract_json_from_text(text)
    if plan:
        return plan, analysis, architecture, report, reasoning

    plan, analysis, architecture, report, reasoning = try_fix_and_parse_json(text)
    if plan:
        return plan, analysis, architecture, report, reasoning

    plan, analysis = parse_text_to_plan(text)
    if plan:
        return plan, analysis, None, None, ""

    return [], None, None, None, ""


def strip_markdown_code_blocks(text: str) -> str:
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if len(lines) > 2:
            return "\n".join(lines[1:-1]).strip()
        if len(lines) > 1:
            return "\n".join(lines[1:]).strip()
    return text


def try_extract_json_from_text(
    text: str,
) -> tuple[PlanSteps, PlanAnalysis, PlanArchitecture, PlanReport, str]:
    candidates = []
    depth = 0
    start = -1

    for i, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start = i
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidates.append(text[start : i + 1])

    for candidate in candidates:
        try:
            data = json.loads(candidate)
            plan, analysis, architecture, report, reasoning = extract_plan_data(data)
            if plan:
                return plan, analysis, architecture, report, reasoning
        except json.JSONDecodeError:
            continue

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            plan, analysis, architecture, report, reasoning = extract_plan_data(data)
            if plan:
                return plan, analysis, architecture, report, reasoning
        except json.JSONDecodeError:
            pass

    return [], None, None, None, ""


def try_fix_and_parse_json(
    text: str,
) -> tuple[PlanSteps, PlanAnalysis, PlanArchitecture, PlanReport, str]:
    cleaned = strip_markdown_code_blocks(text)
    json_text = cleaned
    start = json_text.find("{")
    if start >= 0:
        json_text = json_text[start:]
    end = json_text.rfind("}")
    if end >= 0:
        json_text = json_text[: end + 1]

    json_text = re.sub(r",\s*([}\]])", r"\1", json_text)
    if '"' not in json_text:
        json_text = json_text.replace("'", '"')
    json_text = re.sub(r"//.*?$", "", json_text, flags=re.MULTILINE)
    json_text = re.sub(r"/\*.*?\*/", "", json_text, flags=re.DOTALL)

    try:
        data = json.loads(json_text)
        plan, analysis, architecture, report, reasoning = extract_plan_data(data)
        if plan:
            return plan, analysis, architecture, report, reasoning
    except json.JSONDecodeError:
        pass

    return [], None, None, None, ""


def parse_text_to_plan(text: str) -> tuple[PlanSteps, PlanAnalysis]:
    steps: PlanSteps = []
    numbered_pattern = re.compile(
        r"(?:step\s*)?(\d+)[.:)\-]\s*(.+?)(?=(?:\n\s*(?:step\s*)?\d+[.:)\-])|$)",
        re.IGNORECASE | re.DOTALL,
    )

    matches = list(numbered_pattern.finditer(text))
    if matches:
        for match in matches:
            step_num = int(match.group(1))
            description = match.group(2).strip()
            if "\n" in description:
                lines = [line.strip() for line in description.split("\n") if line.strip()]
                description = lines[0]
            steps.append(_make_step(step_num, description))

    if not steps:
        bullet_pattern = re.compile(r"^[\-\*]\s+(.+?)$", re.MULTILINE)
        for i, desc in enumerate(bullet_pattern.findall(text), 1):
            steps.append(_make_step(i, desc.strip()))

    if not steps:
        return [], None

    analysis = {
        "task_summary": text[:200].strip(),
        "complexity": "medium",
        "clarifying_questions": [],
        "constraints": [],
    }
    return steps, analysis


def _make_step(step_num: int, description: str) -> dict[str, Any]:
    return {
        "step": step_num,
        "description": description,
        "tools_needed": infer_tools_from_text(description),
        "expected_output": f"Step {step_num} completed",
        "success_criteria": f"Step {step_num} criteria met",
        "depends_on": [],
        "parallel_group": None,
        "subagent_type": None,
    }


def infer_tools_from_text(text: str) -> list:
    text_lower = text.lower()
    tools = []
    if any(kw in text_lower for kw in ["file", "write", "create", "save", "edit", "modify"]):
        tools.append("write_file")
    if any(kw in text_lower for kw in ["run", "execute", "command", "install", "build", "terminal", "shell"]):
        tools.append("terminal")
    if any(kw in text_lower for kw in ["read", "view", "cat", "open", "load"]):
        tools.append("read_file")
    if any(kw in text_lower for kw in ["search", "find", "grep", "look up", "web"]):
        tools.append("web_search")
    if any(kw in text_lower for kw in ["database", "db", "sql", "query"]):
        tools.append("database")
    return tools


def _normalize_string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _normalize_development_report(raw: Any) -> PlanReport:
    if not isinstance(raw, dict):
        return None

    summary = raw.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    priorities = raw.get("priorities", {})
    if not isinstance(priorities, dict):
        priorities = {}

    estimates = raw.get("estimates", {})
    if not isinstance(estimates, dict):
        estimates = {}

    stack = raw.get("stack", {})
    if not isinstance(stack, dict):
        stack = {}

    stages = []
    for stage in raw.get("development_stages", []) or []:
        if not isinstance(stage, dict):
            continue
        stages.append({
            "stage": stage.get("stage", len(stages)),
            "title": stage.get("title", ""),
            "items": _normalize_string_list(stage.get("items")),
            "duration_hours": str(stage.get("duration_hours", "")).strip(),
            "story_points": stage.get("story_points"),
        })

    dependencies = []
    for dep in raw.get("dependencies", []) or []:
        if not isinstance(dep, dict):
            continue
        dependencies.append({
            "task": dep.get("task", ""),
            "depends_on": dep.get("depends_on", ""),
            "unblocks": dep.get("unblocks", ""),
        })

    blockers = []
    for blocker in raw.get("blockers", []) or []:
        if not isinstance(blocker, dict):
            continue
        blockers.append({
            "risk": blocker.get("risk", ""),
            "probability": blocker.get("probability", ""),
            "impact": blocker.get("impact", ""),
            "mitigation": blocker.get("mitigation", ""),
        })

    manual_actions = []
    for action in raw.get("manual_actions", []) or []:
        if not isinstance(action, dict):
            continue
        manual_actions.append({
            "action": action.get("action", ""),
            "when": action.get("when", ""),
            "who": action.get("who", ""),
        })

    estimate_stages = []
    for est in estimates.get("stages", []) or []:
        if not isinstance(est, dict):
            continue
        estimate_stages.append({
            "stage": est.get("stage", len(estimate_stages)),
            "title": est.get("title", ""),
            "hours": est.get("hours"),
            "story_points": est.get("story_points"),
        })

    technologies = []
    for tech in stack.get("technologies", []) or []:
        if isinstance(tech, dict):
            technologies.append({
                "component": tech.get("component", tech.get("name", "")),
                "choice": tech.get("choice", tech.get("value", "")),
            })
        elif isinstance(tech, str) and tech.strip():
            technologies.append({"component": "", "choice": tech.strip()})

    report = {
        "title": raw.get("title", "").strip(),
        "summary": {
            "goal": summary.get("goal", ""),
            "key_decisions": _normalize_string_list(summary.get("key_decisions")),
            "critical_risks": _normalize_string_list(summary.get("critical_risks")),
        },
        "development_stages": stages,
        "priorities": {
            "mvp": _normalize_string_list(priorities.get("mvp")),
            "important_later": _normalize_string_list(
                priorities.get("important_later", priorities.get("later"))
            ),
            "optional": _normalize_string_list(priorities.get("optional")),
        },
        "dependencies": dependencies,
        "blockers": blockers,
        "manual_actions": manual_actions,
        "estimates": {
            "stages": estimate_stages,
            "total_hours": estimates.get("total_hours"),
            "total_story_points": estimates.get("total_story_points"),
            "calendar_time": estimates.get("calendar_time", ""),
            "buffer_note": estimates.get("buffer_note", ""),
        },
        "stack": {
            "technologies": technologies,
            "patterns": _normalize_string_list(stack.get("patterns")),
            "critical_fixes": _normalize_string_list(stack.get("critical_fixes")),
        },
        "parallel_work_notes": _normalize_string_list(raw.get("parallel_work_notes")),
    }

    has_content = any([
        report["title"],
        report["summary"]["goal"],
        report["summary"]["key_decisions"],
        report["summary"]["critical_risks"],
        report["development_stages"],
        report["priorities"]["mvp"],
        report["dependencies"],
        report["blockers"],
        report["manual_actions"],
        report["estimates"]["stages"],
        report["stack"]["technologies"],
    ])
    return report if has_content else None


def extract_plan_data(
    data: dict,
) -> tuple[PlanSteps, PlanAnalysis, PlanArchitecture, PlanReport, str]:
    analysis = data.get("analysis", {})
    if analysis:
        analysis = {
            "task_summary": analysis.get("task_summary", ""),
            "complexity": analysis.get("complexity", "medium"),
            "needs_clarification": bool(analysis.get("needs_clarification", False)),
            "ambiguity_level": analysis.get("ambiguity_level", "low"),
            "clarification_reason": analysis.get("clarification_reason", ""),
            "clarifying_questions": analysis.get("clarifying_questions", []),
            "constraints": analysis.get("constraints", []),
        }
    else:
        analysis = None

    architecture = data.get("architecture", {})
    if architecture:
        risks = architecture.get("risks", [])
        if isinstance(risks, list) and risks and isinstance(risks[0], dict):
            risks = [
                {"risk": r.get("risk", ""), "mitigation": r.get("mitigation", "")}
                for r in risks
            ]
        architecture = {
            "approach": architecture.get("approach", ""),
            "tech_stack": architecture.get("tech_stack", []),
            "structure": architecture.get("structure", ""),
            "risks": risks,
        }
    else:
        architecture = None

    report = _normalize_development_report(data.get("development_report"))

    reasoning = str(data.get("reasoning", "")).strip()

    raw_plan = data.get("plan", [])
    if not isinstance(raw_plan, list):
        raw_plan = []

    steps = []
    for i, step in enumerate(raw_plan):
        steps.append({
            "step": step.get("step", i + 1),
            "description": step.get("description", ""),
            "tools_needed": step.get("tools_needed", []),
            "expected_output": step.get("expected_output", ""),
            "success_criteria": step.get("success_criteria", ""),
            "depends_on": step.get("depends_on", []),
            "parallel_group": step.get("parallel_group"),
            "subagent_type": step.get("subagent_type"),
        })

    return steps, analysis, architecture, report, reasoning