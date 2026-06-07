"""Plan response parsing (JSON, markdown-wrapped, plain-text fallbacks)."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

PlanSteps = List[Dict[str, Any]]
PlanAnalysis = Optional[Dict[str, Any]]
PlanArchitecture = Optional[Dict[str, Any]]


def parse_detailed_plan(text: str) -> Tuple[PlanSteps, PlanAnalysis, PlanArchitecture]:
    """Parse LLM plan response into structured plan, analysis, and architecture."""
    text = text.strip()
    if not text:
        return [], None, None

    try:
        data = json.loads(text)
        plan, analysis, architecture = extract_plan_data(data)
        if plan:
            return plan, analysis, architecture
    except json.JSONDecodeError:
        pass

    cleaned = strip_markdown_code_blocks(text)
    if cleaned != text:
        try:
            data = json.loads(cleaned)
            plan, analysis, architecture = extract_plan_data(data)
            if plan:
                return plan, analysis, architecture
        except json.JSONDecodeError:
            pass
        plan, analysis, architecture = try_extract_json_from_text(cleaned)
        if plan:
            return plan, analysis, architecture

    plan, analysis, architecture = try_extract_json_from_text(text)
    if plan:
        return plan, analysis, architecture

    plan, analysis, architecture = try_fix_and_parse_json(text)
    if plan:
        return plan, analysis, architecture

    plan, analysis = parse_text_to_plan(text)
    if plan:
        return plan, analysis, None

    return [], None, None


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


def try_extract_json_from_text(text: str) -> Tuple[PlanSteps, PlanAnalysis, PlanArchitecture]:
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
            plan, analysis, architecture = extract_plan_data(data)
            if plan:
                return plan, analysis, architecture
        except json.JSONDecodeError:
            continue

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            plan, analysis, architecture = extract_plan_data(data)
            if plan:
                return plan, analysis, architecture
        except json.JSONDecodeError:
            pass

    return [], None, None


def try_fix_and_parse_json(text: str) -> Tuple[PlanSteps, PlanAnalysis, PlanArchitecture]:
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
        plan, analysis, architecture = extract_plan_data(data)
        if plan:
            return plan, analysis, architecture
    except json.JSONDecodeError:
        pass

    return [], None, None


def parse_text_to_plan(text: str) -> Tuple[PlanSteps, PlanAnalysis]:
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


def _make_step(step_num: int, description: str) -> Dict[str, Any]:
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


def extract_plan_data(data: dict) -> Tuple[PlanSteps, PlanAnalysis, PlanArchitecture]:
    analysis = data.get("analysis", {})
    if analysis:
        analysis = {
            "task_summary": analysis.get("task_summary", ""),
            "complexity": analysis.get("complexity", "medium"),
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

    return steps, analysis, architecture


