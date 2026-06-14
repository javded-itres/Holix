"""
Plan Markdown Builder — generates rich Markdown from plan data.

Used by plan_review_node to render plans as Markdown in the chat log
instead of a modal dialog. This module is the single source of truth
for plan rendering format.
"""

from __future__ import annotations

from core.i18n.locale import normalize_locale
from core.i18n.messages import t


def build_plan_markdown(
    plan_steps: list,
    step_count: int = 0,
    reasoning: str = "",
    user_input: str = "",
    analysis: dict | None = None,
    architecture: dict | None = None,
    *,
    locale: str | None = None,
) -> str:
    """Build a rich Markdown document from the plan data."""
    loc = normalize_locale(locale)
    sections = []
    count = step_count or len(plan_steps)

    sections.append(f"# {t('plan.title', loc, count=count)}")
    if user_input:
        display_input = user_input[:300] + ("…" if len(user_input) > 300 else "")
        sections.append(f"\n> **{t('plan.task_label', loc)}** {display_input}\n")

    if analysis:
        sections.append("\n---\n")
        sections.append(f"## {t('plan.analysis', loc)}")

        task_summary = analysis.get("task_summary", "")
        complexity = analysis.get("complexity", "medium")
        questions = analysis.get("clarifying_questions", [])
        constraints = analysis.get("constraints", [])

        if task_summary:
            sections.append(f"\n**{t('plan.summary', loc)}** {task_summary}\n")

        comp_emoji = {"simple": "🟢", "medium": "🟡", "complex": "🔴"}.get(complexity, "🟡")
        sections.append(
            f"\n**{t('plan.complexity', loc)}** {comp_emoji} {complexity.capitalize()}\n"
        )

        if questions:
            sections.append(f"\n### {t('plan.questions', loc)}\n")
            for i, q in enumerate(questions[:5], 1):
                sections.append(f"{i}. {q}")
            sections.append(f"\n*{t('plan.questions_hint', loc)}*\n")

        if constraints:
            sections.append(f"\n### {t('plan.constraints', loc)}\n")
            for c in constraints[:5]:
                sections.append(f"- {c}")
            sections.append("")

    if architecture:
        sections.append("\n---\n")
        sections.append(f"## {t('plan.architecture', loc)}")

        approach = architecture.get("approach", "")
        tech_stack = architecture.get("tech_stack", [])
        structure = architecture.get("structure", "")

        if approach:
            sections.append(f"\n**{t('plan.approach', loc)}** {approach}\n")
        if tech_stack:
            sections.append(
                f"\n**{t('plan.tech_stack', loc)}** " + " · ".join(tech_stack[:10]) + "\n"
            )
        if structure:
            sections.append(f"\n**{t('plan.structure', loc)}** {structure}\n")

        risks = architecture.get("risks", [])
        if risks:
            sections.append(f"\n### {t('plan.risks', loc)}\n")
            sections.append(f"| {t('plan.risk_col', loc)} | {t('plan.mitigation_col', loc)} |")
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
    sections.append(f"## {t('plan.steps', loc)}\n")

    for step in plan_steps:
        num = step.get("step", "?")
        desc = step.get("description", t("plan.no_description", loc))
        tools = step.get("tools_needed", [])
        expected = step.get("expected_output", "")
        criteria = step.get("success_criteria", "")
        depends_on = step.get("depends_on", [])
        parallel = step.get("parallel_group")
        subagent = (step.get("subagent_type") or "").strip()

        sections.append(f"### {t('plan.step', loc, num=num)}: {desc}\n")

        meta_parts = []
        if tools:
            meta_parts.append(
                f"**{t('plan.tools', loc)}** " + ", ".join(f"`{tool}`" for tool in tools)
            )
        if subagent:
            meta_parts.append(f"**{t('plan.subagent', loc)}** `{subagent}`")
        if parallel is not None:
            meta_parts.append(f"**{t('plan.parallel', loc)}** {parallel}")
        if depends_on:
            deps = ", ".join(str(d) for d in depends_on)
            meta_parts.append(f"**{t('plan.depends', loc)}** {deps}")
        if meta_parts:
            sections.append("\n" + " · ".join(meta_parts) + "\n")

        if expected:
            sections.append(f"- **{t('plan.expected', loc)}** {expected}")
        if criteria:
            sections.append(f"- **{t('plan.success', loc)}** {criteria}")

        sections.append("")

    if reasoning:
        sections.append("\n---\n")
        sections.append(f"## {t('plan.reasoning', loc)}\n\n{reasoning}\n")

    return "\n".join(sections)