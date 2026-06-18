"""
Plan Node — generates a comprehensive, detailed execution plan from user input.

Used in plan_and_execute and hybrid execution modes. The LLM performs:
1. Task analysis (complexity, constraints, clarifying questions)
2. Architecture design (approach, tech stack, structure)
3. Risk assessment (risks and mitigations)
4. Detailed execution plan (steps with tools, dependencies, parallelism)

If plan_refinement_feedback is non-empty, appends it so the LLM can regenerate
an improved plan based on user feedback.

If the task is ambiguous, the agent should list clarifying questions in the
analysis section. The plan_review UI will display these questions and the
user can provide answers via the "refine" option, which triggers plan
regeneration with the user's answers appended as refinement_feedback.
"""

import asyncio
import logging

from langchain_core.runnables import RunnableConfig

from core.graph.state import HolixGraphState, get_agent_from_config
from core.plan_review.parser import (
    is_development_report_complete,
    is_truncated_json,
    parse_detailed_plan,
)

# Backward-compatible re-exports for tests
_parse_detailed_plan = parse_detailed_plan

logger = logging.getLogger(__name__)

DETAILED_PLAN_PROMPT = """You are a senior software architect and task planner. Analyze the task and create a comprehensive execution plan.

## TASK
{task}

## CONTEXT FROM MEMORY
{context}

## AVAILABLE TOOLS
{tools}

## PROJECT HANDBOOK
{project_handbook}

## CRITICAL RULES
1. NEVER return a single-step plan unless the task is truly trivial (e.g., "what is 2+2?")
2. For any non-trivial task, break it into AT LEAST 3 steps
3. Each step must be CONCRETE and ACTIONABLE — specify exactly what to do and which tools to use
4. Fill in ALL fields — empty analysis/architecture is not acceptable
5. If the task is ambiguous, list clarifying questions but STILL provide a plan

## INSTRUCTIONS

### Phase 1: Analysis & Clarification
- Read the task carefully and identify what exactly needs to be done
- If the task is ambiguous, incomplete, or could be interpreted multiple ways:
  * Set `needs_clarification` to true
  * Set `ambiguity_level` to "high" or "medium"
  * Explain why in `clarification_reason`
  * List concrete questions in `clarifying_questions` (at least 1, at most 5)
  * Do NOT pretend the task is clear — the user will be asked these questions BEFORE plan approval
- Only set `needs_clarification` to false when the task is truly unambiguous
- Examples of when to ask questions:
  * The task doesn't specify which technology/framework to use
  * The scope is unclear (e.g., "build an app" — what features?)
  * Requirements are contradictory or missing
  * Multiple valid architectures exist and the choice materially affects the plan
- Identify constraints and dependencies
- Assess complexity: simple / medium / complex

### Phase 2: Architecture & Technical Design
- Technical approach and design decisions
- Technology stack to use
- File/module structure
- Data models and key interfaces

### Phase 3: Risk Assessment
- Technical risks and their mitigations
- Potential failure points

### Phase 4: Execution Plan
For each step, provide:
- A clear, actionable description (what to do and which tools to use)
- Expected output / deliverable
- Success criteria (how to verify the step succeeded)
- Dependencies on other steps (step numbers)
- Whether this step can run in parallel with others (parallel_group: null or integer)

### Phase 5: Parallelism & Efficiency
- Identify which steps can run in parallel
- Mark parallel steps with the same parallel_group number

### Phase 6: Development Report (for user approval before execution)
Produce a structured `development_report` that the user reviews before development starts.
For non-trivial tasks this report MUST be complete — empty sections are not acceptable.

The report must include:
1. **Summary** — goal, key architectural decisions, critical risks
2. **Development stages** — numbered stages (Этап 0, 1, 2…) with bullet items and duration estimates
3. **Priorities** — MVP blockers, important-but-later, optional/future
4. **Dependencies** — table: task → depends on → what it unblocks
5. **Blockers & risks** — probability, impact, mitigation for each risk
6. **Manual actions** — action, when, who (developer/DevOps/architect)
7. **Estimates** — per-stage hours + story points, total, calendar time, buffer note
8. **Stack & architecture** — technology choices, patterns, critical fixes vs original spec

Align `development_stages` with high-level milestones; keep `plan` as concrete agent execution steps.

## EXAMPLE OUTPUT
For a task like "Create a REST API for a blog", a good plan would look like:
{{
    "analysis": {{
        "task_summary": "Build a REST API for a blog with CRUD endpoints",
        "complexity": "medium",
        "needs_clarification": true,
        "ambiguity_level": "medium",
        "clarification_reason": "Framework not specified",
        "clarifying_questions": ["Which framework?"],
        "constraints": ["Must use Python"]
    }},
    "architecture": {{
        "approach": "FastAPI backend with SQLAlchemy ORM and PostgreSQL",
        "tech_stack": ["Python", "FastAPI", "SQLAlchemy", "PostgreSQL"],
        "structure": "app/main.py, app/models/, app/routes/, app/database.py",
        "risks": [{{"risk": "Migration conflicts", "mitigation": "Use Alembic versioning"}}]
    }},
    "plan": [
        {{"step": 1, "description": "Initialize FastAPI project with dependencies", "tools_needed": ["terminal"], "expected_output": "Project structure created", "success_criteria": "FastAPI app runs", "depends_on": [], "parallel_group": null, "subagent_type": null}},
        {{"step": 2, "description": "Define SQLAlchemy models for Post, Comment, User", "tools_needed": ["write_file"], "expected_output": "Models defined in app/models/", "success_criteria": "Models import without errors", "depends_on": [1], "parallel_group": null, "subagent_type": null}},
        {{"step": 3, "description": "Create CRUD routes for /posts, /comments, /users", "tools_needed": ["write_file"], "expected_output": "Route files in app/routes/", "success_criteria": "Endpoints respond to HTTP requests", "depends_on": [2], "parallel_group": null, "subagent_type": null}},
        {{"step": 4, "description": "Add JWT authentication middleware", "tools_needed": ["write_file"], "expected_output": "Auth middleware in app/auth.py", "success_criteria": "Protected endpoints require token", "depends_on": [3], "parallel_group": null, "subagent_type": null}},
        {{"step": 5, "description": "Write unit tests for all endpoints", "tools_needed": ["write_file", "terminal"], "expected_output": "Tests in tests/", "success_criteria": "All tests pass", "depends_on": [4], "parallel_group": null, "subagent_type": null}}
    ],
    "reasoning": "Sequential: project setup → models → routes → auth → tests",
    "development_report": {{
        "title": "Development Plan: Blog REST API",
        "summary": {{
            "goal": "Build a REST API for a blog with CRUD endpoints",
            "key_decisions": ["FastAPI + SQLAlchemy + PostgreSQL", "JWT auth"],
            "critical_risks": ["Schema migration conflicts without versioning"]
        }},
        "development_stages": [
            {{
                "stage": 0,
                "title": "Project setup",
                "items": ["Initialize FastAPI project", "Configure PostgreSQL"],
                "duration_hours": "2-4",
                "story_points": 3
            }}
        ],
        "priorities": {{
            "mvp": ["Stage 0: project setup", "Stage 1: models and routes"],
            "important_later": ["Load testing"],
            "optional": ["Admin dashboard"]
        }},
        "dependencies": [
            {{"task": "Stage 0", "depends_on": "—", "unblocks": "All other stages"}}
        ],
        "blockers": [
            {{"risk": "Migration conflicts", "probability": "medium", "impact": "high", "mitigation": "Use Alembic"}}
        ],
        "manual_actions": [
            {{"action": "Provision PostgreSQL", "when": "Before Stage 0", "who": "DevOps"}}
        ],
        "estimates": {{
            "stages": [{{"stage": 0, "title": "Project setup", "hours": 3, "story_points": 3}}],
            "total_hours": 20,
            "total_story_points": 20,
            "calendar_time": "3-4 days",
            "buffer_note": "+20% for integration issues"
        }},
        "stack": {{
            "technologies": [
                {{"component": "Framework", "choice": "FastAPI"}},
                {{"component": "ORM", "choice": "SQLAlchemy"}}
            ],
            "patterns": ["Layered API + repository pattern"],
            "critical_fixes": ["Add Alembic migrations from day one"]
        }},
        "parallel_work_notes": ["Models and routes can be developed in parallel after setup"]
    }}
}}

Now create a plan for the task above. Respond with ONLY valid JSON:
{{
    "analysis": {{
        "task_summary": "...",
        "complexity": "simple|medium|complex",
        "needs_clarification": true,
        "ambiguity_level": "low|medium|high",
        "clarification_reason": "...",
        "clarifying_questions": ["..."],
        "constraints": ["..."]
    }},
    "architecture": {{
        "approach": "...",
        "tech_stack": ["..."],
        "structure": "...",
        "risks": [{{"risk": "...", "mitigation": "..."}}]
    }},
    "development_report": {{
        "title": "Development Plan: ...",
        "summary": {{
            "goal": "...",
            "key_decisions": ["..."],
            "critical_risks": ["..."]
        }},
        "development_stages": [
            {{
                "stage": 0,
                "title": "...",
                "items": ["..."],
                "duration_hours": "4-6",
                "story_points": 5
            }}
        ],
        "priorities": {{
            "mvp": ["..."],
            "important_later": ["..."],
            "optional": ["..."]
        }},
        "dependencies": [
            {{"task": "...", "depends_on": "...", "unblocks": "..."}}
        ],
        "blockers": [
            {{"risk": "...", "probability": "high|medium|low", "impact": "high|medium|low", "mitigation": "..."}}
        ],
        "manual_actions": [
            {{"action": "...", "when": "...", "who": "..."}}
        ],
        "estimates": {{
            "stages": [{{"stage": 0, "title": "...", "hours": 5, "story_points": 5}}],
            "total_hours": 0,
            "total_story_points": 0,
            "calendar_time": "...",
            "buffer_note": "..."
        }},
        "stack": {{
            "technologies": [{{"component": "...", "choice": "..."}}],
            "patterns": ["..."],
            "critical_fixes": ["..."]
        }},
        "parallel_work_notes": ["..."]
    }},
    "plan": [
        {{
            "step": 1,
            "description": "...",
            "tools_needed": ["..."],
            "expected_output": "...",
            "success_criteria": "...",
            "depends_on": [],
            "parallel_group": null,
            "subagent_type": null
        }}
    ],
    "reasoning": "..."
}}"""

SUBAGENT_PLAN_APPENDIX = """
## Sub-agent delegation (enabled)
When the user assigns work to specific agents, copy those exact type names into `subagent_type`
on the matching plan steps (built-in: coder, web_researcher, researcher, analyst, reviewer, writer;
plus any custom types defined in the profile).
When complexity is medium or complex, you MUST assign `subagent_type` on steps that specialists should run.
At least one step in medium/complex plans should use a sub-agent.
Mapping:
- research / web search → `web_researcher` or `researcher`
- coding / implementation → `coder`
- data / SQL analysis → `analyst`
- code review → `reviewer`
- documentation → `writer`
For complex tasks, use `parallel_group` (same integer) for independent steps that can run in parallel.
Use `depends_on` so downstream steps wait for prerequisites.
Leave `subagent_type` null only for short coordination steps the main agent must handle directly.
"""

FALLBACK_PLAN_PROMPT = """You are a task planner. Break down the following task into clear, ordered sub-tasks.

Task: {task}

Respond with ONLY valid JSON:
{{
    "analysis": {{
        "task_summary": "One-sentence summary",
        "complexity": "medium",
        "clarifying_questions": [],
        "constraints": []
    }},
    "architecture": {{
        "approach": "Overall approach",
        "tech_stack": [],
        "structure": "Key structure",
        "risks": []
    }},
    "plan": [
        {{
            "step": 1,
            "description": "Description of sub-task 1",
            "tools_needed": ["terminal"],
            "expected_output": "What this step should produce",
            "success_criteria": "How to verify success",
            "depends_on": [],
            "parallel_group": null,
            "subagent_type": null
        }}
    ],
    "reasoning": "Brief explanation"
}}"""


async def plan_node(state: HolixGraphState, config: RunnableConfig) -> dict:
    """Generate a comprehensive plan from the user's input.

    Uses the LLM to analyze the task, design architecture, assess risks,
    and create a detailed execution plan with steps, dependencies, and
    parallelism.

    Features:
    - Timeout enforcement via plan_generation_timeout setting
    - Retry logic via plan_generation_retries setting
    - JSON mode for providers that support it
    - Rich error logging so failures are diagnosable
    - Clarifying questions in analysis when task is ambiguous

    If plan_refinement_feedback is non-empty, appends it to the prompt
    so the LLM can generate an improved plan based on user feedback.

    Args:
        state: Current graph state with user_input.
        config: RunnableConfig with agent at config["configurable"]["_agent"].

    Returns:
        Partial state update with plan_steps, plan_analysis, plan_architecture,
        plan_report, plan_reasoning, and reset plan_review fields.
    """
    agent = get_agent_from_config(config)
    user_input = state.get("user_input", "")
    conversation_id = state.get("conversation_id", "default")
    refinement_feedback = state.get("plan_refinement_feedback", "")

    if not agent:
        # No agent available — create a simple single-step plan
        return {
            "plan_steps": [{
                "step": 1,
                "description": user_input,
                "tools_needed": [],
                "expected_output": "Complete response to the user's request",
                "success_criteria": "Task completed successfully",
                "depends_on": [],
                "parallel_group": None,
                "subagent_type": None,
            }],
            "current_plan_step": 0,
            "plan_status": "pending_review",
            "plan_refinement_feedback": "",
            "plan_analysis": {"task_summary": user_input[:200], "complexity": "medium", "clarifying_questions": [], "constraints": []},
            "plan_architecture": {"approach": "Direct execution", "tech_stack": [], "structure": "", "risks": []},
            "plan_report": None,
            "plan_reasoning": "",
        }

    # Load timeout and retry settings
    cfg = getattr(agent, "config", None)
    try:
        from config import settings as app_settings

        default_timeout = float(app_settings.plan_generation_timeout)
        default_retries = int(app_settings.plan_generation_retries)
        default_max_tokens = int(app_settings.plan_generation_max_tokens)
    except Exception:
        default_timeout = 600.0
        default_retries = 2
        default_max_tokens = 12000

    if cfg is not None:
        plan_timeout = float(getattr(cfg, "plan_generation_timeout", default_timeout))
        plan_retries = int(getattr(cfg, "plan_generation_retries", default_retries))
        plan_max_tokens = int(getattr(cfg, "plan_generation_max_tokens", default_max_tokens))
    else:
        plan_timeout = default_timeout
        plan_retries = default_retries
        plan_max_tokens = default_max_tokens

    # Build context from memory
    context_parts = []
    relevant_memories = state.get("relevant_memories", [])
    if relevant_memories:
        for mem in relevant_memories[:5]:
            content = mem.get("content", "")[:200]
            source = mem.get("source", "unknown")
            context_parts.append(f"[{source}]: {content}")

    relevant_strategies = state.get("relevant_strategies", [])
    if relevant_strategies:
        for s in relevant_strategies[:3]:
            key = s.get("key", "")
            content = s.get("content", "")[:200]
            context_parts.append(f"[Strategy: {key}]: {content}")

    context = "\n".join(context_parts) if context_parts else "No relevant context available."

    from core.project.holix_md import format_holix_md_block, planning_context_note

    project_handbook = format_holix_md_block()
    if not project_handbook:
        project_handbook = (
            f"{planning_context_note()} "
            "No `.holix/HOLIX.md` yet — run `/init` in this repo to generate it."
        )

    # Build tools description
    tools_desc = _get_tools_description(agent)

    from core.profile.soul import profile_name_from_agent
    from core.prompt_builder import language_instruction_block

    profile_name = profile_name_from_agent(agent)
    lang_block = language_instruction_block(profile_name=profile_name)

    from core.plan_review.plan_storage import format_saved_plans_context

    saved_plans_context = format_saved_plans_context(getattr(agent, "config", None))

    # Choose prompt: detailed if tools available, fallback otherwise
    if tools_desc:
        prompt = DETAILED_PLAN_PROMPT.format(
            task=user_input,
            context=context,
            tools=tools_desc,
            project_handbook=project_handbook,
        )
    else:
        prompt = FALLBACK_PLAN_PROMPT.format(task=user_input)
        if project_handbook:
            prompt += f"\n\n## PROJECT HANDBOOK\n{project_handbook}\n"

    prompt = f"{lang_block}\n\n{prompt}"
    prompt += f"\n\n## SAVED PROJECT PLANS\n{saved_plans_context}\n"

    from core.config_utils import is_subagents_enabled

    if is_subagents_enabled(agent.config):
        prompt += SUBAGENT_PLAN_APPENDIX

    # Append refinement feedback if the user requested changes to a previous plan
    if refinement_feedback:
        prompt += (
            "\n\n## Refinement Feedback\n"
            "The user requested changes to the previous plan:\n"
            f"{refinement_feedback}\n\n"
            "Please generate an improved plan addressing this feedback."
        )

    if hasattr(agent, "emit"):
        from core.agent_events import ThinkingEvent
        from core.i18n.live_ui import live_generating_plan_label

        agent.emit(
            ThinkingEvent(
                message=live_generating_plan_label(profile_name, timeout=int(plan_timeout)),
                conversation_id=conversation_id,
            )
        )

    # Call LLM with timeout + retry
    client = agent.client
    model = agent.model
    plan_system = (
        "You are a senior software architect and task planner. "
        "Create comprehensive, detailed execution plans. "
        "Respond with ONLY valid JSON. "
        "Write ALL human-readable text fields in the plan (task_summary, descriptions, "
        "development_report, analysis, architecture, questions, reasoning) in the language "
        "required below; "
        "keep JSON keys in English.\n\n"
        f"{lang_block}"
    )

    api_kwargs = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": plan_system,
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": plan_max_tokens,
    }

    result_text = None
    last_error = None
    use_json_mode = True
    attempt_timeout = plan_timeout

    for attempt in range(1 + plan_retries):
        try:
            logger.info(
                f"Plan generation attempt {attempt + 1}/{1 + plan_retries} "
                f"(model={model}, timeout={attempt_timeout}s, "
                f"max_tokens={api_kwargs['max_tokens']}, json_mode={use_json_mode})"
            )

            # Try with response_format first, fallback without
            if use_json_mode:
                try:
                    kwargs = {**api_kwargs, "response_format": {"type": "json_object"}}
                    response = await asyncio.wait_for(
                        client.chat.completions.create(**kwargs),
                        timeout=attempt_timeout,
                    )
                except (TypeError, ValueError, NotImplementedError) as fmt_err:
                    # response_format not supported by this provider
                    logger.debug(f"response_format not supported: {fmt_err}, retrying without")
                    use_json_mode = False
                    response = await asyncio.wait_for(
                        client.chat.completions.create(**api_kwargs),
                        timeout=attempt_timeout,
                    )
                except TimeoutError:
                    raise  # Let outer handler catch it
            else:
                response = await asyncio.wait_for(
                    client.chat.completions.create(**api_kwargs),
                    timeout=attempt_timeout,
                )

            result_text = response.choices[0].message.content or ""
            logger.info(
                f"Plan LLM response received: {len(result_text)} chars "
                f"(first 200: {result_text[:200]})"
            )

            if not result_text.strip():
                logger.warning("Plan LLM returned empty response, retrying...")
                continue

            if is_truncated_json(result_text):
                last_error = "Truncated JSON response (likely max_tokens or timeout)"
                logger.warning(
                    f"Plan generation produced truncated JSON on attempt "
                    f"{attempt + 1}/{1 + plan_retries}"
                )
                result_text = None
                if attempt < plan_retries:
                    continue
                break

            parsed_plan, parsed_analysis, _, parsed_report, _ = parse_detailed_plan(result_text)
            complexity = (parsed_analysis or {}).get("complexity", "medium")
            needs_full_report = complexity in ("medium", "complex") or len(parsed_plan) >= 3
            if needs_full_report and not is_development_report_complete(parsed_report):
                last_error = "Incomplete development_report"
                logger.warning(
                    f"Plan generation missing required development_report sections on attempt "
                    f"{attempt + 1}/{1 + plan_retries}"
                )
                result_text = None
                if attempt < plan_retries:
                    prompt += (
                        "\n\n## IMPORTANT\n"
                        "Your previous response was incomplete. Return the FULL JSON with a "
                        "complete `development_report` (all 8 sections) and at least 3 plan steps."
                    )
                    api_kwargs["messages"] = [
                        api_kwargs["messages"][0],
                        {"role": "user", "content": prompt},
                    ]
                    continue
                break

            break

        except TimeoutError:
            last_error = f"Timeout after {attempt_timeout}s"
            logger.warning(
                f"Plan generation timed out on attempt {attempt + 1}/{1 + plan_retries} "
                f"(timeout={attempt_timeout}s)"
            )
            result_text = None
            if attempt < plan_retries:
                attempt_timeout = min(attempt_timeout * 1.5, 900.0)
                logger.info(f"Increasing timeout to {attempt_timeout}s for next attempt")
            continue

        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            logger.warning(
                f"Plan generation failed on attempt {attempt + 1}/{1 + plan_retries}: "
                f"{type(e).__name__}: {e}"
            )
            if attempt < plan_retries:
                # On generic error, try without JSON mode
                if use_json_mode:
                    use_json_mode = False
                    logger.info("Retrying without response_format for next attempt")
            continue

    # Parse the LLM response
    if result_text and result_text.strip():
        plan, analysis, architecture, plan_report, plan_reasoning = parse_detailed_plan(result_text)

        if not plan:
            logger.warning(
                f"Plan parsing returned empty despite getting LLM response. "
                f"Raw text (500 chars): {result_text[:500]}"
            )
            # Fallback: single-step plan
            plan = [{
                "step": 1,
                "description": user_input,
                "tools_needed": [],
                "expected_output": "Complete response to the user's request",
                "success_criteria": "Task completed successfully",
                "depends_on": [],
                "parallel_group": None,
                "subagent_type": None,
            }]
            analysis = analysis or {"task_summary": user_input[:200], "complexity": "medium", "clarifying_questions": [], "constraints": []}
            architecture = architecture or {"approach": "Direct execution", "tech_stack": [], "structure": "", "risks": []}
    else:
        # All retries exhausted or no response
        logger.error(
            f"Plan generation failed after all retries. Last error: {last_error}. "
            f"Falling back to single-step plan."
        )
        plan = [{
            "step": 1,
            "description": user_input,
            "tools_needed": [],
            "expected_output": "Complete response to the user's request",
            "success_criteria": "Task completed successfully",
            "depends_on": [],
            "parallel_group": None,
            "subagent_type": None,
        }]
        analysis = {"task_summary": user_input[:200], "complexity": "medium", "clarifying_questions": [], "constraints": []}
        architecture = {"approach": "Direct execution", "tech_stack": [], "structure": "", "risks": []}
        plan_report = None
        plan_reasoning = ""

    logger.info(f"Plan generated with {len(plan)} steps for: {user_input[:80]}...")

    import uuid

    plan_id = f"plan_{uuid.uuid4().hex[:10]}"
    if hasattr(agent, "set_plan_id"):
        agent.set_plan_id(plan_id)

    # Emit plan generated event
    if hasattr(agent, "emit"):
        from core.agent_events import PlanGeneratedEvent
        agent.emit(PlanGeneratedEvent(
            plan_steps=plan,
            step_count=len(plan),
            conversation_id=conversation_id,
            plan_id=plan_id,
        ))

    update: dict = {
        "plan_id": plan_id,
        "plan_steps": plan,
        "current_plan_step": 0,
        "plan_status": "pending_review",
        "plan_refinement_feedback": "",
        "plan_analysis": analysis,
        "plan_architecture": architecture,
        "plan_report": plan_report,
        "plan_reasoning": plan_reasoning,
    }
    if not refinement_feedback:
        update["plan_clarification_rounds"] = 0
    return update


def _get_tools_description(agent) -> str:
    """Get a formatted description of available tools for the plan prompt."""
    try:
        if not hasattr(agent, "tools") or not agent.tools:
            return "All available tools (terminal, file operations, web search, etc.)"

        tools = agent.tools.list_tools()
        if not tools:
            return "All available tools (terminal, file operations, web search, etc.)"

        descriptions = []
        for tool in tools:
            name = getattr(tool, "name", str(tool))
            desc = getattr(tool, "description", "")[:100]
            descriptions.append(f"- {name}: {desc}")

        return "\n".join(descriptions)
    except Exception:
        return "All available tools (terminal, file operations, web search, etc.)"
