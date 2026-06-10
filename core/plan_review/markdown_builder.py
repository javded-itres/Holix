"""
Plan Markdown Builder — generates rich Markdown from plan data.

Used by plan_review_node to render plans as Markdown in the chat log
instead of a modal dialog. This module is the single source of truth
for plan rendering format.
"""



def build_plan_markdown(
    plan_steps: list,
    step_count: int = 0,
    reasoning: str = "",
    user_input: str = "",
    analysis: dict | None = None,
    architecture: dict | None = None,
) -> str:
    """Build a rich Markdown document from the plan data.

    Produces a single, well-structured Markdown string suitable for
    rendering in RichLog via rich.markdown.Markdown.

    Args:
        plan_steps: List of step dicts from plan_node.
        step_count: Number of steps.
        reasoning: Brief explanation of the plan order.
        user_input: The original user query.
        analysis: Task analysis dict.
        architecture: Architecture dict.

    Returns:
        Markdown string.
    """
    sections = []

    # ── Title ────────────────────────────────────────────────────────
    sections.append(f"# 📋 Execution Plan — {step_count or len(plan_steps)} steps")
    if user_input:
        display_input = user_input[:300] + ("…" if len(user_input) > 300 else "")
        sections.append(f"\n> **Task:** {display_input}\n")

    # ── Analysis ─────────────────────────────────────────────────────
    if analysis:
        sections.append("\n---\n")
        sections.append("## 📊 Analysis")

        task_summary = analysis.get("task_summary", "")
        complexity = analysis.get("complexity", "medium")
        questions = analysis.get("clarifying_questions", [])
        constraints = analysis.get("constraints", [])

        if task_summary:
            sections.append(f"\n**Summary:** {task_summary}\n")

        # Complexity badge
        comp_emoji = {"simple": "🟢", "medium": "🟡", "complex": "🔴"}.get(complexity, "🟡")
        sections.append(f"\n**Complexity:** {comp_emoji} {complexity.capitalize()}\n")

        if questions:
            sections.append("\n### ❓ Clarifying Questions\n")
            for i, q in enumerate(questions[:5], 1):
                sections.append(f"{i}. {q}")
            sections.append("\n*Describe what you'd like to change to answer these questions.*\n")

        if constraints:
            sections.append("\n### 🔒 Constraints\n")
            for c in constraints[:5]:
                sections.append(f"- {c}")
            sections.append("")

    # ── Architecture ─────────────────────────────────────────────────
    if architecture:
        sections.append("\n---\n")
        sections.append("## 🏗️ Architecture")

        approach = architecture.get("approach", "")
        tech_stack = architecture.get("tech_stack", [])
        structure = architecture.get("structure", "")

        if approach:
            sections.append(f"\n**Approach:** {approach}\n")
        if tech_stack:
            sections.append("\n**Tech Stack:** " + " · ".join(tech_stack[:10]) + "\n")
        if structure:
            sections.append(f"\n**Structure:** {structure}\n")

        # Risks
        risks = architecture.get("risks", [])
        if risks:
            sections.append("\n### ⚡ Risks & Mitigations\n")
            sections.append("| Risk | Mitigation |")
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

    # ── Plan Steps ───────────────────────────────────────────────────
    sections.append("\n---\n")
    sections.append("## 📝 Execution Steps\n")

    for step in plan_steps:
        num = step.get("step", "?")
        desc = step.get("description", "No description")
        tools = step.get("tools_needed", [])
        expected = step.get("expected_output", "")
        criteria = step.get("success_criteria", "")
        depends_on = step.get("depends_on", [])
        parallel = step.get("parallel_group")

        sections.append(f"### Step {num}: {desc}\n")

        # Metadata line
        meta_parts = []
        if tools:
            meta_parts.append("**Tools:** " + ", ".join(f"`{t}`" for t in tools))
        if parallel is not None:
            meta_parts.append(f"**Parallel group:** {parallel}")
        if depends_on:
            deps = ", ".join(str(d) for d in depends_on)
            meta_parts.append(f"**Depends on:** step {deps}")
        if meta_parts:
            sections.append("\n" + " · ".join(meta_parts) + "\n")

        if expected:
            sections.append(f"- **Expected output:** {expected}")
        if criteria:
            sections.append(f"- **Success criteria:** {criteria}")

        sections.append("")

    # ── Reasoning ────────────────────────────────────────────────────
    if reasoning:
        sections.append("\n---\n")
        sections.append(f"## 💭 Reasoning\n\n{reasoning}\n")

    return "\n".join(sections)