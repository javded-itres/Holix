"""
Plan Markdown Builder — generates rich Markdown from plan data.

Used by plan_review_node to render plans as Markdown in the chat log
instead of a modal dialog. This module is the single source of truth
for plan rendering format.
"""

from __future__ import annotations

from typing import Any

from core.i18n.locale import normalize_locale
from core.i18n.messages import t


def build_plan_markdown(
    plan_steps: list,
    step_count: int = 0,
    reasoning: str = "",
    user_input: str = "",
    analysis: dict | None = None,
    architecture: dict | None = None,
    plan_report: dict | None = None,
    *,
    locale: str | None = None,
) -> str:
    """Build a rich Markdown document from the plan data."""
    loc = normalize_locale(locale)
    if plan_report:
        return _build_development_report_markdown(
            plan_steps=plan_steps,
            step_count=step_count or len(plan_steps),
            reasoning=reasoning,
            user_input=user_input,
            analysis=analysis,
            architecture=architecture,
            plan_report=plan_report,
            locale=loc,
        )
    return _build_legacy_plan_markdown(
        plan_steps=plan_steps,
        step_count=step_count or len(plan_steps),
        reasoning=reasoning,
        user_input=user_input,
        analysis=analysis,
        architecture=architecture,
        locale=loc,
    )


def _build_development_report_markdown(
    *,
    plan_steps: list,
    step_count: int,
    reasoning: str,
    user_input: str,
    analysis: dict | None,
    architecture: dict | None,
    plan_report: dict,
    locale: str,
) -> str:
    sections: list[str] = []
    title = plan_report.get("title") or t("plan.report.default_title", locale)
    sections.append(f"# {title}")

    if user_input:
        display_input = user_input[:300] + ("…" if len(user_input) > 300 else "")
        sections.append(f"\n> **{t('plan.task_label', locale)}** {display_input}\n")

    summary = plan_report.get("summary", {})
    sections.append(f"\n## {t('plan.report.section_summary', locale)}\n")
    goal = summary.get("goal", "")
    if goal:
        sections.append(f"**{t('plan.report.goal', locale)}** {goal}\n")
    key_decisions = summary.get("key_decisions", [])
    if key_decisions:
        sections.append(f"\n**{t('plan.report.key_decisions', locale)}**\n")
        for item in key_decisions:
            sections.append(f"- {item}")
        sections.append("")
    critical_risks = summary.get("critical_risks", [])
    if critical_risks:
        sections.append(f"\n**{t('plan.report.critical_risks', locale)}**\n")
        for item in critical_risks:
            sections.append(f"- {item}")
        sections.append("")

    stages = plan_report.get("development_stages", [])
    if stages:
        sections.append(f"\n## {t('plan.report.section_stages', locale)}\n")
        for stage in stages:
            stage_num = stage.get("stage", "?")
            stage_title = stage.get("title", "")
            sections.append(f"### {t('plan.report.stage', locale, num=stage_num)}. {stage_title}\n")
            for item in stage.get("items", []):
                sections.append(f"- {item}")
            duration = stage.get("duration_hours", "")
            if duration:
                sections.append(
                    f"\n*{t('plan.report.duration', locale)}* {duration}"
                )
            sections.append("")

    priorities = plan_report.get("priorities", {})
    if any(priorities.get(key) for key in ("mvp", "important_later", "optional")):
        sections.append(f"\n## {t('plan.report.section_priorities', locale)}\n")
        if priorities.get("mvp"):
            sections.append(f"### {t('plan.report.priority_mvp', locale)}\n")
            for item in priorities["mvp"]:
                sections.append(f"- {item}")
            sections.append("")
        if priorities.get("important_later"):
            sections.append(f"### {t('plan.report.priority_later', locale)}\n")
            for item in priorities["important_later"]:
                sections.append(f"- {item}")
            sections.append("")
        if priorities.get("optional"):
            sections.append(f"### {t('plan.report.priority_optional', locale)}\n")
            for item in priorities["optional"]:
                sections.append(f"- {item}")
            sections.append("")

    dependencies = plan_report.get("dependencies", [])
    if dependencies:
        sections.append(f"\n## {t('plan.report.section_dependencies', locale)}\n")
        sections.append(
            f"| {t('plan.report.dep_task', locale)} | "
            f"{t('plan.report.dep_depends', locale)} | "
            f"{t('plan.report.dep_unblocks', locale)} |"
        )
        sections.append("|---|---|---|")
        for dep in dependencies:
            sections.append(
                f"| {dep.get('task', '')} | {dep.get('depends_on', '')} | {dep.get('unblocks', '')} |"
            )
        sections.append("")

    parallel_notes = plan_report.get("parallel_work_notes", [])
    if parallel_notes:
        sections.append(f"**{t('plan.report.parallel_work', locale)}**\n")
        for note in parallel_notes:
            sections.append(f"- {note}")
        sections.append("")

    blockers = plan_report.get("blockers", [])
    if blockers:
        sections.append(f"\n## {t('plan.report.section_blockers', locale)}\n")
        sections.append(
            f"| {t('plan.report.blocker_risk', locale)} | "
            f"{t('plan.report.blocker_probability', locale)} | "
            f"{t('plan.report.blocker_impact', locale)} | "
            f"{t('plan.report.blocker_mitigation', locale)} |"
        )
        sections.append("|---|---|---|---|")
        for blocker in blockers:
            sections.append(
                f"| {blocker.get('risk', '')} | {blocker.get('probability', '')} | "
                f"{blocker.get('impact', '')} | {blocker.get('mitigation', '')} |"
            )
        sections.append("")

    manual_actions = plan_report.get("manual_actions", [])
    if manual_actions:
        sections.append(f"\n## {t('plan.report.section_manual', locale)}\n")
        sections.append(
            f"| {t('plan.report.manual_action', locale)} | "
            f"{t('plan.report.manual_when', locale)} | "
            f"{t('plan.report.manual_who', locale)} |"
        )
        sections.append("|---|---|---|")
        for action in manual_actions:
            sections.append(
                f"| {action.get('action', '')} | {action.get('when', '')} | {action.get('who', '')} |"
            )
        sections.append("")

    estimates = plan_report.get("estimates", {})
    estimate_stages = estimates.get("stages", [])
    if estimate_stages or estimates.get("total_hours"):
        sections.append(f"\n## {t('plan.report.section_estimates', locale)}\n")
        if estimate_stages:
            sections.append(
                f"| {t('plan.report.estimate_stage', locale)} | "
                f"{t('plan.report.estimate_hours', locale)} | "
                f"{t('plan.report.estimate_sp', locale)} |"
            )
            sections.append("|---|---|---|")
            for est in estimate_stages:
                stage_label = est.get("title") or t(
                    "plan.report.stage", locale, num=est.get("stage", "?")
                )
                hours = est.get("hours", "")
                sp = est.get("story_points", "")
                sections.append(f"| {stage_label} | {hours} | {sp} |")
            sections.append("")
        total_hours = estimates.get("total_hours")
        total_sp = estimates.get("total_story_points")
        if total_hours is not None or total_sp is not None:
            sections.append(
                f"**{t('plan.report.total', locale)}** "
                f"{total_hours or '—'} {t('plan.report.hours_unit', locale)}, "
                f"~{total_sp or '—'} SP\n"
            )
        calendar_time = estimates.get("calendar_time", "")
        if calendar_time:
            sections.append(f"**{t('plan.report.calendar', locale)}** {calendar_time}\n")
        buffer_note = estimates.get("buffer_note", "")
        if buffer_note:
            sections.append(f"**{t('plan.report.buffer', locale)}** {buffer_note}\n")

    stack = plan_report.get("stack", {})
    if stack.get("technologies") or stack.get("patterns") or stack.get("critical_fixes"):
        sections.append(f"\n## {t('plan.report.section_stack', locale)}\n")
        technologies = stack.get("technologies", [])
        if technologies:
            sections.append(f"### {t('plan.report.stack_tech', locale)}\n")
            for tech in technologies:
                component = tech.get("component", "")
                choice = tech.get("choice", "")
                if component:
                    sections.append(f"- **{component}:** {choice}")
                else:
                    sections.append(f"- {choice}")
            sections.append("")
        patterns = stack.get("patterns", [])
        if patterns:
            sections.append(f"### {t('plan.report.stack_patterns', locale)}\n")
            for pattern in patterns:
                sections.append(f"- {pattern}")
            sections.append("")
        fixes = stack.get("critical_fixes", [])
        if fixes:
            sections.append(f"### {t('plan.report.stack_fixes', locale)}\n")
            for fix in fixes:
                sections.append(f"- {fix}")
            sections.append("")

    if analysis:
        questions = analysis.get("clarifying_questions", [])
        if questions:
            sections.append(f"\n## {t('plan.questions', locale)}\n")
            for i, q in enumerate(questions[:5], 1):
                sections.append(f"{i}. {q}")
            sections.append(f"\n*{t('plan.questions_hint', locale)}*\n")

    sections.append("\n---\n")
    sections.append(f"## {t('plan.steps', locale)} ({step_count})\n")
    sections.extend(_render_execution_steps(plan_steps, locale))

    if reasoning:
        sections.append("\n---\n")
        sections.append(f"## {t('plan.reasoning', locale)}\n\n{reasoning}\n")

    sections.append(f"\n*{t('plan.approval_hint', locale)}*\n")
    return "\n".join(sections)


def _build_legacy_plan_markdown(
    *,
    plan_steps: list,
    step_count: int,
    reasoning: str,
    user_input: str,
    analysis: dict | None,
    architecture: dict | None,
    locale: str,
) -> str:
    sections: list[str] = []

    sections.append(f"# {t('plan.title', locale, count=step_count)}")
    if user_input:
        display_input = user_input[:300] + ("…" if len(user_input) > 300 else "")
        sections.append(f"\n> **{t('plan.task_label', locale)}** {display_input}\n")

    if analysis:
        sections.append("\n---\n")
        sections.append(f"## {t('plan.analysis', locale)}")

        task_summary = analysis.get("task_summary", "")
        complexity = analysis.get("complexity", "medium")
        questions = analysis.get("clarifying_questions", [])
        constraints = analysis.get("constraints", [])

        if task_summary:
            sections.append(f"\n**{t('plan.summary', locale)}** {task_summary}\n")

        comp_emoji = {"simple": "🟢", "medium": "🟡", "complex": "🔴"}.get(complexity, "🟡")
        sections.append(
            f"\n**{t('plan.complexity', locale)}** {comp_emoji} {complexity.capitalize()}\n"
        )

        if questions:
            sections.append(f"\n### {t('plan.questions', locale)}\n")
            for i, q in enumerate(questions[:5], 1):
                sections.append(f"{i}. {q}")
            sections.append(f"\n*{t('plan.questions_hint', locale)}*\n")

        if constraints:
            sections.append(f"\n### {t('plan.constraints', locale)}\n")
            for c in constraints[:5]:
                sections.append(f"- {c}")
            sections.append("")

    if architecture:
        sections.append("\n---\n")
        sections.append(f"## {t('plan.architecture', locale)}")

        approach = architecture.get("approach", "")
        tech_stack = architecture.get("tech_stack", [])
        structure = architecture.get("structure", "")

        if approach:
            sections.append(f"\n**{t('plan.approach', locale)}** {approach}\n")
        if tech_stack:
            sections.append(
                f"\n**{t('plan.tech_stack', locale)}** " + " · ".join(tech_stack[:10]) + "\n"
            )
        if structure:
            sections.append(f"\n**{t('plan.structure', locale)}** {structure}\n")

        risks = architecture.get("risks", [])
        if risks:
            sections.append(f"\n### {t('plan.risks', locale)}\n")
            sections.append(f"| {t('plan.risk_col', locale)} | {t('plan.mitigation_col', locale)} |")
            sections.append("|------|-----------|")
            for r in risks[:6]:
                if isinstance(r, dict):
                    risk_text = r.get("risk", "")
                    mitigation = r.get("mitigation", "")
                else:
                    risk_text = str(r)
                    mitigation = ""
                sections.append(f"| {risk_text[:80]} | {mitigation[:80]} |")
            sections.append("")

    sections.append("\n---\n")
    sections.append(f"## {t('plan.steps', locale)}\n")
    sections.extend(_render_execution_steps(plan_steps, locale))

    if reasoning:
        sections.append("\n---\n")
        sections.append(f"## {t('plan.reasoning', locale)}\n\n{reasoning}\n")

    sections.append(f"\n*{t('plan.approval_hint', locale)}*\n")
    return "\n".join(sections)


def _render_execution_steps(plan_steps: list, locale: str) -> list[str]:
    sections: list[str] = []
    for step in plan_steps:
        num = step.get("step", "?")
        desc = step.get("description", t("plan.no_description", locale))
        tools = step.get("tools_needed", [])
        expected = step.get("expected_output", "")
        criteria = step.get("success_criteria", "")
        depends_on = step.get("depends_on", [])
        parallel = step.get("parallel_group")
        subagent = (step.get("subagent_type") or "").strip()

        sections.append(f"### {t('plan.step', locale, num=num)}: {desc}\n")

        meta_parts = []
        if tools:
            meta_parts.append(
                f"**{t('plan.tools', locale)}** " + ", ".join(f"`{tool}`" for tool in tools)
            )
        if subagent:
            meta_parts.append(f"**{t('plan.subagent', locale)}** `{subagent}`")
        if parallel is not None:
            meta_parts.append(f"**{t('plan.parallel', locale)}** {parallel}")
        if depends_on:
            deps = ", ".join(str(d) for d in depends_on)
            meta_parts.append(f"**{t('plan.depends', locale)}** {deps}")
        if meta_parts:
            sections.append("\n" + " · ".join(meta_parts) + "\n")

        if expected:
            sections.append(f"- **{t('plan.expected', locale)}** {expected}")
        if criteria:
            sections.append(f"- **{t('plan.success', locale)}** {criteria}")

        sections.append("")
    return sections