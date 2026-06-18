"""Build sub-agent orchestration waves from plan_and_execute state."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from core.subagents.registry import subagent_type_names

_SUBAGENT_TYPE_ALIASES: dict[str, str] = {
    "coder": "coder",
    "кодер": "coder",
    "разработчик": "coder",
    "developer": "coder",
    "researcher": "researcher",
    "исследователь": "researcher",
    "web_researcher": "web_researcher",
    "web-researcher": "web_researcher",
    "analyst": "analyst",
    "аналитик": "analyst",
    "reviewer": "reviewer",
    "ревьюер": "reviewer",
    "writer": "writer",
    "писатель": "writer",
}

_DESCRIPTION_AGENT_PATTERNS = (
    re.compile(r"@([A-Za-z][\w-]*)", re.IGNORECASE),
    re.compile(
        r"(?:субагент|sub-?agent|агент|agent)\s*[:—-]\s*([A-Za-z][\w-]*)",
        re.IGNORECASE,
    ),
    re.compile(r"\[([A-Za-z][\w-]*)\]"),
)


@dataclass(slots=True)
class SubagentTask:
    agent_type: str
    task: str
    step_ref: int
    step_index: int


@dataclass(slots=True)
class OrchestrationWave:
    wave_id: int
    tasks: list[SubagentTask] = field(default_factory=list)


@dataclass(slots=True)
class OrchestrationPlan:
    complexity: str
    enabled: bool
    waves: list[OrchestrationWave] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "complexity": self.complexity,
            "enabled": self.enabled,
            "reasoning": self.reasoning,
            "waves": [
                {
                    "wave_id": wave.wave_id,
                    "tasks": [
                        {
                            "agent_type": t.agent_type,
                            "task": t.task,
                            "step_ref": t.step_ref,
                            "step_index": t.step_index,
                        }
                        for t in wave.tasks
                    ],
                }
                for wave in self.waves
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrchestrationPlan:
        waves = []
        for wave_data in data.get("waves", []):
            tasks = [
                SubagentTask(
                    agent_type=t["agent_type"],
                    task=t["task"],
                    step_ref=int(t["step_ref"]),
                    step_index=int(t["step_index"]),
                )
                for t in wave_data.get("tasks", [])
            ]
            waves.append(OrchestrationWave(wave_id=int(wave_data["wave_id"]), tasks=tasks))
        return cls(
            complexity=str(data.get("complexity", "medium")),
            enabled=bool(data.get("enabled", False)),
            waves=waves,
            reasoning=str(data.get("reasoning", "")),
        )


def _resolve_subagent_type_name(
    raw: str,
    *,
    profile: str | None = None,
) -> str | None:
    token = (raw or "").strip().lstrip("@")
    if not token:
        return None

    known = subagent_type_names(profile=profile)
    lowered = token.lower()
    base = re.sub(r"[-_]\d+$", "", lowered)

    if token in known:
        return token
    if base in known:
        return base

    alias = _SUBAGENT_TYPE_ALIASES.get(base) or _SUBAGENT_TYPE_ALIASES.get(lowered)
    if alias and alias in known:
        return alias

    for candidate in (base, lowered, alias or ""):
        if not candidate:
            continue
        for known_name in known:
            if known_name.lower() == candidate:
                return known_name
    return None


def _subagent_type_from_description(
    description: str,
    *,
    profile: str | None = None,
) -> str | None:
    for pattern in _DESCRIPTION_AGENT_PATTERNS:
        match = pattern.search(description or "")
        if not match:
            continue
        resolved = _resolve_subagent_type_name(match.group(1), profile=profile)
        if resolved:
            return resolved
    return None


def _plan_has_explicit_subagent_assignments(
    plan_steps: list[dict[str, Any]],
    *,
    profile: str | None = None,
) -> bool:
    for step in plan_steps:
        explicit = (step.get("subagent_type") or "").strip()
        if explicit and _resolve_subagent_type_name(explicit, profile=profile):
            return True
        if _subagent_type_from_description(step.get("description") or "", profile=profile):
            return True
    return False


def infer_subagent_type(
    step: dict[str, Any],
    *,
    profile: str | None = None,
) -> str | None:
    """Resolve sub-agent type from plan step metadata or heuristics."""
    explicit = (step.get("subagent_type") or "").strip()
    if explicit:
        resolved = _resolve_subagent_type_name(explicit, profile=profile)
        if resolved:
            return resolved

    from_description = _subagent_type_from_description(
        step.get("description") or "",
        profile=profile,
    )
    if from_description:
        return from_description

    description = (step.get("description") or "").lower()
    tools = [str(t).lower() for t in (step.get("tools_needed") or [])]

    if any(t in tools for t in ("web_search", "web_fetch")):
        return "web_researcher"
    if any(t in tools for t in ("sql_query", "sql_schema", "database")):
        return "analyst"
    if any(t in tools for t in ("write_file", "run_terminal_command", "terminal", "code_executor")):
        return "coder"

    if any(
        kw in description
        for kw in (
            "research",
            "search",
            "investigate",
            "look up",
            "исслед",
            "поиск",
            "найти",
            "изучить",
            "собрать информацию",
            "проанализировать рынок",
        )
    ):
        return "web_researcher"
    if any(
        kw in description
        for kw in (
            "implement",
            "code",
            "build",
            "debug",
            "fix",
            "refactor",
            "код",
            "реализ",
            "написать",
            "исправ",
            "отлад",
            "разработ",
            "создать скрипт",
            "программ",
        )
    ):
        return "coder"
    if any(kw in description for kw in ("analy", "анализ данных", "sql", "база данных", "метрик")):
        return "analyst"
    if any(kw in description for kw in ("review", "ревью", "проверить код", "код-ревью")):
        return "reviewer"
    if any(
        kw in description
        for kw in (
            "document",
            "readme",
            "documentation",
            "write doc",
            "документ",
            "документац",
            "описание api",
            "readme",
        )
    ):
        return "writer"
    return None


def _completed_step_numbers(plan_steps: list[dict[str, Any]], current_step_index: int) -> set[int]:
    done: set[int] = set()
    for idx in range(max(0, current_step_index)):
        if idx < len(plan_steps):
            done.add(int(plan_steps[idx].get("step", idx + 1)))
    return done


def _deps_satisfied(step: dict[str, Any], completed: set[int]) -> bool:
    depends_on = step.get("depends_on") or []
    if not depends_on:
        return True
    return all(int(dep) in completed for dep in depends_on)


def _eligible_steps(
    plan_steps: list[dict[str, Any]],
    *,
    current_step_index: int,
    profile: str | None = None,
) -> list[tuple[int, dict[str, Any], str]]:
    """Return (index, step, agent_type) for steps ready to delegate."""
    completed = _completed_step_numbers(plan_steps, current_step_index)
    eligible: list[tuple[int, dict[str, Any], str]] = []
    for idx in range(current_step_index, len(plan_steps)):
        step = plan_steps[idx]
        if not _deps_satisfied(step, completed):
            continue
        agent_type = infer_subagent_type(step, profile=profile)
        if not agent_type:
            continue
        task = (step.get("description") or "").strip()
        if not task:
            continue
        eligible.append((idx, step, agent_type))
    return eligible


def _cap_tasks(
    items: list[SubagentTask],
    max_concurrent: int,
) -> list[SubagentTask]:
    limit = max(1, int(max_concurrent or 4))
    return items[:limit]


def _build_medium_waves(eligible: list[tuple[int, dict[str, Any], str]]) -> list[OrchestrationWave]:
    tasks = [
        SubagentTask(
            agent_type=agent_type,
            task=(step.get("description") or "").strip(),
            step_ref=int(step.get("step", idx + 1)),
            step_index=idx,
        )
        for idx, step, agent_type in eligible
    ]
    if not tasks:
        return []
    return [OrchestrationWave(wave_id=0, tasks=tasks)]


def _build_complex_waves(
    plan_steps: list[dict[str, Any]],
    *,
    current_step_index: int,
    profile: str | None = None,
) -> list[OrchestrationWave]:
    """Build multiple waves respecting depends_on and parallel_group."""
    completed = _completed_step_numbers(plan_steps, current_step_index)
    scheduled_indices: set[int] = set(range(current_step_index))
    waves: list[OrchestrationWave] = []
    wave_id = 0

    while True:
        eligible: list[tuple[int, dict[str, Any], str]] = []
        for idx in range(len(plan_steps)):
            if idx in scheduled_indices:
                continue
            step = plan_steps[idx]
            if not _deps_satisfied(step, completed):
                continue
            agent_type = infer_subagent_type(step, profile=profile)
            if not agent_type:
                continue
            task = (step.get("description") or "").strip()
            if not task:
                continue
            eligible.append((idx, step, agent_type))

        if not eligible:
            break

        buckets: dict[str, list[tuple[int, dict[str, Any], str]]] = {}
        for idx, step, agent_type in eligible:
            pg = step.get("parallel_group")
            key = f"pg:{pg}" if pg is not None else f"solo:{idx}"
            buckets.setdefault(key, []).append((idx, step, agent_type))

        next_key = min(
            buckets.keys(),
            key=lambda k: min(item[0] for item in buckets[k]),
        )
        batch = buckets.pop(next_key)
        tasks = [
            SubagentTask(
                agent_type=agent_type,
                task=(step.get("description") or "").strip(),
                step_ref=int(step.get("step", idx + 1)),
                step_index=idx,
            )
            for idx, step, agent_type in batch
        ]
        waves.append(OrchestrationWave(wave_id=wave_id, tasks=tasks))
        wave_id += 1

        for idx, step, _ in batch:
            scheduled_indices.add(idx)
            completed.add(int(step.get("step", idx + 1)))

    return waves


def build_orchestration_plan(
    *,
    plan_analysis: dict[str, Any] | None,
    plan_steps: list[dict[str, Any]],
    current_step_index: int = 0,
    enable_subagents: bool = False,
    max_concurrent: int = 4,
    profile: str | None = None,
) -> OrchestrationPlan:
    """Decide whether and how to run sub-agents for the remaining plan."""
    analysis = plan_analysis or {}
    complexity = str(analysis.get("complexity", "medium")).strip().lower()

    has_explicit_assignments = _plan_has_explicit_subagent_assignments(
        plan_steps,
        profile=profile,
    )

    if not enable_subagents:
        return OrchestrationPlan(
            complexity=complexity,
            enabled=False,
            reasoning="sub-agents disabled",
        )

    if complexity == "simple" and not has_explicit_assignments:
        return OrchestrationPlan(
            complexity=complexity,
            enabled=False,
            reasoning="task complexity is simple and no explicit sub-agent assignments",
        )

    eligible = _eligible_steps(
        plan_steps,
        current_step_index=current_step_index,
        profile=profile,
    )
    if not eligible:
        return OrchestrationPlan(
            complexity=complexity,
            enabled=False,
            reasoning="no plan steps match sub-agent delegation",
        )

    if complexity == "medium":
        waves = _build_medium_waves(eligible)
        reasoning = "medium: single parallel wave for eligible steps"
    else:
        waves = _build_complex_waves(
            plan_steps,
            current_step_index=current_step_index,
            profile=profile,
        )
        reasoning = "complex: waves by parallel_group and dependencies"

    for wave in waves:
        wave.tasks = _cap_tasks(wave.tasks, max_concurrent)

    waves = [w for w in waves if w.tasks]
    if not waves:
        return OrchestrationPlan(
            complexity=complexity,
            enabled=False,
            reasoning="no tasks after concurrency limits",
        )

    return OrchestrationPlan(
        complexity=complexity,
        enabled=True,
        waves=waves,
        reasoning=reasoning,
    )


def current_wave(plan: OrchestrationPlan, wave_index: int) -> OrchestrationWave | None:
    if not plan.enabled or wave_index < 0 or wave_index >= len(plan.waves):
        return None
    return plan.waves[wave_index]


def format_wave_user_summary(
    *,
    wave_id: int,
    total_waves: int,
    results: dict[str, dict[str, Any]],
    task_meta: dict[str, SubagentTask],
) -> str:
    """Short user-visible summary for messenger delivery."""
    completed = sum(1 for r in results.values() if r.get("success"))
    total = len(results)
    lines = [
        f"**Субагенты** (волна {wave_id + 1}/{total_waves}): {completed}/{total} готово",
        "",
    ]
    for job_id, payload in results.items():
        meta = task_meta.get(job_id)
        agent_type = meta.agent_type if meta else "?"
        status = "✓" if payload.get("success") else "✗"
        body = (payload.get("response") or payload.get("error") or "").strip()
        preview = body[:1800] + ("…" if len(body) > 1800 else "")
        lines.append(f"{status} `{job_id}` ({agent_type})")
        if preview:
            lines.append(preview)
        lines.append("")
    return "\n".join(lines).strip()


def format_wave_aggregate(
    *,
    wave_id: int,
    total_waves: int,
    results: dict[str, dict[str, Any]],
    task_meta: dict[str, SubagentTask],
) -> str:
    """Build markdown context for main-agent synthesis in react."""
    completed = sum(1 for r in results.values() if r.get("success"))
    total = len(results)
    lines = [
        f"[Sub-agents wave {wave_id + 1}/{total_waves} — {completed}/{total} completed]",
        "",
        "Synthesize the sub-agent outputs below into a coherent progress update for the user.",
        "Highlight successes, failures, and concrete deliverables.",
        "",
    ]
    for job_id, payload in results.items():
        meta = task_meta.get(job_id)
        step_label = f"step {meta.step_ref}" if meta else "step ?"
        status = "✓" if payload.get("success") else "✗"
        lines.append(f"### {job_id} ({step_label}) {status}")
        body = payload.get("response") or payload.get("error") or ""
        lines.append(str(body)[:4000])
        lines.append("")
    return "\n".join(lines).strip()