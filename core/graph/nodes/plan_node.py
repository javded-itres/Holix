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

from core.graph.state import HelixGraphState, get_agent_from_config
from core.plan_review.parser import parse_detailed_plan

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
- If the task is ambiguous, incomplete, or could be interpreted multiple ways, you MUST list clarifying questions in the "clarifying_questions" field
- Examples of when to ask questions:
  * The task doesn't specify which technology/framework to use
  * The scope is unclear (e.g., "build an app" — what features?)
  * Requirements are contradictory or missing
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

## EXAMPLE OUTPUT
For a task like "Create a REST API for a blog", a good plan would look like:
{{
    "analysis": {{
        "task_summary": "Build a REST API for a blog with CRUD endpoints",
        "complexity": "medium",
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
    "reasoning": "Sequential: project setup → models → routes → auth → tests"
}}

Now create a plan for the task above. Respond with ONLY valid JSON:
{{
    "analysis": {{
        "task_summary": "...",
        "complexity": "simple|medium|complex",
        "clarifying_questions": ["..."],
        "constraints": ["..."]
    }},
    "architecture": {{
        "approach": "...",
        "tech_stack": ["..."],
        "structure": "...",
        "risks": [{{"risk": "...", "mitigation": "..."}}]
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


async def plan_node(state: HelixGraphState, config: RunnableConfig) -> dict:
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
        and reset plan_review fields.
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
        }

    # Load timeout and retry settings
    cfg = getattr(agent, "config", None)
    if cfg is not None and hasattr(cfg, "plan_generation_timeout"):
        plan_timeout = float(cfg.plan_generation_timeout)
        plan_retries = int(cfg.plan_generation_retries)
    else:
        try:
            from config import settings
            plan_timeout = settings.plan_generation_timeout
            plan_retries = settings.plan_generation_retries
        except Exception:
            plan_timeout = 120.0
            plan_retries = 2

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

    from core.project.helix_md import format_helix_md_block, planning_context_note

    project_handbook = format_helix_md_block()
    if not project_handbook:
        project_handbook = (
            f"{planning_context_note()} "
            "No `.helix/HELIX.md` yet — run `/init` in this repo to generate it."
        )

    # Build tools description
    tools_desc = _get_tools_description(agent)

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

    # Append refinement feedback if the user requested changes to a previous plan
    if refinement_feedback:
        prompt += (
            "\n\n## Refinement Feedback\n"
            "The user requested changes to the previous plan:\n"
            f"{refinement_feedback}\n\n"
            "Please generate an improved plan addressing this feedback."
        )

    # Emit thinking event so the UI shows "Generating plan..."
    if hasattr(agent, "emit"):
        from core.agent_events import ThinkingEvent
        agent.emit(ThinkingEvent(
            message=f"Generating execution plan (timeout: {plan_timeout}s)...",
            conversation_id=conversation_id,
        ))

    # Call LLM with timeout + retry
    client = agent.client
    model = agent.model
    profile_name = getattr(getattr(agent, "config", None), "profile_name", None)
    from core.prompt_builder import language_instruction_block

    plan_system = (
        "You are a senior software architect and task planner. "
        "Create comprehensive, detailed execution plans. "
        "Respond with ONLY valid JSON. "
        "Write all human-readable text fields in the plan (descriptions, analysis, questions) "
        "in the language required below; keep JSON keys in English.\n\n"
        f"{language_instruction_block(profile_name=profile_name)}"
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
        "max_tokens": 4000,
    }

    result_text = None
    last_error = None
    use_json_mode = True

    for attempt in range(1 + plan_retries):
        try:
            logger.info(
                f"Plan generation attempt {attempt + 1}/{1 + plan_retries} "
                f"(model={model}, timeout={plan_timeout}s, json_mode={use_json_mode})"
            )

            # Try with response_format first, fallback without
            if use_json_mode:
                try:
                    kwargs = {**api_kwargs, "response_format": {"type": "json_object"}}
                    response = await asyncio.wait_for(
                        client.chat.completions.create(**kwargs),
                        timeout=plan_timeout,
                    )
                except (TypeError, ValueError, NotImplementedError) as fmt_err:
                    # response_format not supported by this provider
                    logger.debug(f"response_format not supported: {fmt_err}, retrying without")
                    use_json_mode = False
                    response = await asyncio.wait_for(
                        client.chat.completions.create(**api_kwargs),
                        timeout=plan_timeout,
                    )
                except TimeoutError:
                    raise  # Let outer handler catch it
            else:
                response = await asyncio.wait_for(
                    client.chat.completions.create(**api_kwargs),
                    timeout=plan_timeout,
                )

            result_text = response.choices[0].message.content or ""
            logger.info(
                f"Plan LLM response received: {len(result_text)} chars "
                f"(first 200: {result_text[:200]})"
            )

            # If we got a non-empty response, break out of retry loop
            if result_text.strip():
                break

            logger.warning("Plan LLM returned empty response, retrying...")

        except TimeoutError:
            last_error = f"Timeout after {plan_timeout}s"
            logger.warning(
                f"Plan generation timed out on attempt {attempt + 1}/{1 + plan_retries} "
                f"(timeout={plan_timeout}s)"
            )
            # On timeout, reduce max_tokens for next attempt to get faster response
            if attempt < plan_retries:
                api_kwargs["max_tokens"] = max(1000, api_kwargs["max_tokens"] // 2)
                logger.info(f"Reducing max_tokens to {api_kwargs['max_tokens']} for next attempt")
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
        plan, analysis, architecture = parse_detailed_plan(result_text)

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

    return {
        "plan_id": plan_id,
        "plan_steps": plan,
        "current_plan_step": 0,
        "plan_status": "pending_review",
        "plan_refinement_feedback": "",
        "plan_analysis": analysis,
        "plan_architecture": architecture,
    }


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
