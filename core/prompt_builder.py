import os
from pathlib import Path
from typing import Any

from core.project.holix_md import HOLIX_MD_REL_PATH, task_context_note


def resolve_agent_working_directory(
    *,
    workspace_root: str | None = None,
    workspace_jail_enabled: bool | None = None,
    working_directory: str | None = None,
) -> str:
    """Directory relative paths and project discovery should use.

    Jail on → profile workspace root. Jail off → process CWD (same for main
    agent and in-process sub-agents). Explicit ``working_directory`` wins.
    """
    if working_directory and str(working_directory).strip():
        try:
            return str(Path(working_directory).expanduser().resolve())
        except OSError:
            return str(working_directory).strip()

    root = (workspace_root or "").strip() or None
    jail = workspace_jail_enabled
    if root is None or jail is None:
        try:
            from core.tools.execution_context import get_workspace_root, is_workspace_jail_enabled

            if jail is None:
                jail = is_workspace_jail_enabled()
            if root is None:
                ctx_root = get_workspace_root()
                if ctx_root and str(ctx_root).strip():
                    root = str(ctx_root).strip()
        except Exception:
            pass

    if jail and root:
        try:
            return str(Path(root).expanduser().resolve())
        except OSError:
            return root

    try:
        return str(Path.cwd().resolve())
    except OSError:
        return str(Path.cwd())


def format_working_directory_block(
    *,
    workspace_root: str | None = None,
    workspace_jail_enabled: bool | None = None,
    working_directory: str | None = None,
) -> str:
    """Tell agents (main + sub) which directory file tools use."""
    root = (workspace_root or "").strip() or None
    jail = workspace_jail_enabled
    if root is None or jail is None:
        try:
            from core.tools.execution_context import get_workspace_root, is_workspace_jail_enabled

            if jail is None:
                jail = is_workspace_jail_enabled()
            if root is None:
                ctx_root = get_workspace_root()
                if ctx_root and str(ctx_root).strip():
                    root = str(ctx_root).strip()
        except Exception:
            pass

    primary = resolve_agent_working_directory(
        workspace_root=root,
        workspace_jail_enabled=jail,
        working_directory=working_directory,
    )

    if jail and root:
        return (
            "## Working directory (shared workspace)\n\n"
            "You share this workspace with the main Holix agent and sibling sub-agents.\n"
            f"**Primary path:** `{primary}`\n\n"
            "Create and edit **all** project files under this directory. "
            "Use paths relative to it (or absolute paths under it). "
            "Do **not** write into the Holix install tree or another profile's workspace. "
            "If a path is unclear, call `list_directory` on `.` first."
        )

    lines = [
        "## Working directory (shared with main agent)\n",
        "You use the **same** process working directory as the main Holix agent "
        "and other sub-agents in this session.",
        f"**CWD (relative paths resolve here):** `{primary}`",
    ]
    if root:
        lines.append(f"**Profile workspace_root** (jail off — not forced): `{root}`")
    lines.append(
        "Prefer paths under the CWD. Start with `list_directory` on `.` if the task "
        "does not give absolute paths. Do not invent another project root."
    )
    return "\n".join(lines)


def format_studio_workspace_block(
    *,
    workspace_root: str | None = None,
    workspace_jail_enabled: bool | None = None,
) -> str:
    """When Holix Studio is running, tell the agent which directory to use for files.

    Prefer the per-session agent workspace (jail root). Process env
    ``HOLIX_STUDIO_WORKSPACE_*`` reflects the *serve* process only — in multi-user
    SaaS that is often the deploy CWD, not the invite user's profile workspace.
    """
    root = (workspace_root or "").strip() or None
    jail = workspace_jail_enabled

    if root is None or jail is None:
        try:
            from core.tools.execution_context import get_workspace_root, is_workspace_jail_enabled

            if jail is None:
                jail = is_workspace_jail_enabled()
            if root is None:
                ctx_root = get_workspace_root()
                if ctx_root and str(ctx_root).strip():
                    root = str(ctx_root).strip()
        except Exception:
            pass

    if jail and root:
        return (
            "## Holix Studio working directory\n\n"
            "Create and edit **all** project files only under this workspace:\n"
            f"`{root}`\n\n"
            "Use paths relative to that directory (or absolute paths under it). "
            "Do **not** write into the Holix install/deploy tree or another user's workspace."
        )

    mode = (os.getenv("HOLIX_STUDIO_WORKSPACE_MODE") or "").strip().lower()
    env_root = (os.getenv("HOLIX_STUDIO_WORKSPACE_ROOT") or "").strip()
    if not mode or not env_root:
        return ""
    if mode == "cwd":
        return (
            "## Holix Studio working directory\n\n"
            f"Studio is in **cwd** mode. Create and edit all project files under:\n"
            f"`{env_root}`\n\n"
            "Use relative paths from that directory. Do **not** use the profile "
            "`workspace/` folder unless the user explicitly asks."
        )
    return (
        "## Holix Studio working directory\n\n"
        f"Studio is in **profile workspace** mode. Create and edit project files only under:\n"
        f"`{env_root}`"
    )


def language_instruction_block(*, locale: str | None = None, profile_name: str | None = None) -> str:
    """Locale-aware language rule for system prompts (/lang en | /lang ru)."""
    from core.i18n.locale import LocaleStore, normalize_locale
    from core.i18n.messages import t

    ui_locale = normalize_locale(locale)
    if profile_name and locale is None:
        ui_locale = LocaleStore(profile_name).get()
    return t("prompt.lang_block", ui_locale)


def build_system_prompt(
    tools_description: str,
    active_skills: list[dict[str, Any]],
    skills_formatted: str = "",
    relevant_memories: str = "",
    *,
    profile_name: str | None = None,
    locale: str | None = None,
    workspace_root: str | None = None,
    workspace_jail_enabled: bool | None = None,
) -> str:
    """Build the system prompt for the agent.

    Args:
        tools_description: Description of available tools
        active_skills: List of active skills
        skills_formatted: Pre-formatted skills string

    Returns:
        Complete system prompt
    """
    prompt = """You are Holix, an autonomous AI agent with the ability to:
- Use tools to interact with the system
- Learn from successful tasks and create reusable skills
- Remember context across conversations
- Improve yourself over time

## Your Capabilities

You have access to the following tools:
{tools}

## Sub-agents (background workers)

When `enable_subagents` is on, delegate heavy or specialized work without blocking the user:
- `delegate_to_subagent(agent_type, task)` — starts a background worker (async or OS process); returns `job_id`
- `wait_subagent_result(job_id)` — collect the answer when needed (user can keep chatting meanwhile)
- `list_subagents()` — running and completed jobs
- `terminate_subagent(job_id)` — cancel a job

Types: researcher, coder, analyst, reviewer, writer, web_researcher.

**When to delegate:** Only when the user explicitly asks to use a sub-agent (e.g. `/subagent-spawn`, "delegate to researcher", "запусти субагента").
Do not auto-spawn sub-agents for ordinary questions — answer yourself or use main-agent tools unless delegation was requested.

**Honesty:** Never claim a sub-agent is running unless you called `delegate_to_subagent` (or `list_subagents` shows it).
When the user asks for status (what you are doing, open tasks, progress) — call `list_subagents()`, state only verified facts, and list concrete next steps.

## Hard rule: never fake completed work

**Absolute rule:** You must not state that an action is done unless a tool in *this turn* returned a successful result that proves it.

- **Forbidden without a successful tool result:** "Готово", "сохранил", "файл создан", "удалил", "I've saved", "successfully created", paths to files you "wrote", checklists of ✅ completed work.
- **Saying you will do it is not doing it.** "Сейчас сохраню / запишу / write_file" without an actual tool call is a failure. Call the tool in the same step; do not end the turn on a promise.
- **Tool failed ⇒ report failure.** If the tool returns an error (permission denied, exit code ≠ 0, not found), say it failed, quote the error, and do **not** claim partial or full success.
- **Only report what tools returned.** After tools run, summarize their actual output. If you did not call a tool, you may only describe intent or ask a question — never invent outcomes.
- **Verify writes/deletes** when the user cares about the file: `write_file` / terminal, then `list_directory` or `read_file` / `ls` before saying the file exists.

## Instructions

1. **Think step-by-step** before taking action
2. **Use tools** whenever you need to interact with the system, read/write files, or execute commands
3. **Break down complex tasks** into smaller, manageable steps
4. **Run what you build** — writing files is not enough; install deps, configure env, start the app, read logs, fix errors, re-run until it works or you hit a blocker you cannot fix alone
5. **Learn from success**: After completing a complex multi-step task successfully, you should consider creating a skill for future use
6. **Be precise**: Always verify your work and handle errors gracefully; never claim "done" without a successful tool result in this turn

## Scheduling: Holix cron vs application timers

These are different things — choose correctly:

| User intent | What to do |
|-------------|------------|
| Build a service/script/worker that runs on an interval (poll API, write logs, jobs inside the project) | **Implement code** (loop, APScheduler, cron inside the app, systemd unit). Start with `start_background_process`. **Do not** call `schedule_cron`. |
| Holix should wake the *agent* on a schedule (send digests, remind, periodic agent checks) | Use `schedule_cron` or tell the user `/cron add <schedule> :: <task>`. Requires gateway. |
| One-shot work now | Run it now with tools — no cron. |

Examples:
- «Создай консольный сервис, который раз в 5 минут ходит на API пользователей…» → write a worker service + background process, **not** Holix cron.
- «Присылай мне сводку каждый день в 10 утра» → `schedule_cron` / `/cron add`.

## Tool Usage Guidelines

- Use `read_file` to examine existing code or configuration
- Use `write_file` to create or modify files
- Use `run_terminal_command` for one-shot commands (git, tests, package install) with a timeout
- Use `start_background_process` (alias `run_project`) for dev servers and long-running apps — never block the chat with `npm run dev`, `uvicorn`, etc. Do **not** use `run_terminal_command` for servers.
- Multiple dev servers are allowed on **different ports** (e.g. frontend :3000 + API :8000); only stop or restart when reusing the **same** port
- Always keep the **same port** from the project config/README — never hop to 8001, 8002… unless the user explicitly asks
- After `start_background_process`, call `check_background_process` — it reports which PID listens on each expected port (`ours` vs `foreign`)
- If status is `wrong_process_on_port`, `port_in_use`, `crashed`, `error_in_log`, or `port_not_listening`: read the log, fix code if needed, then `restart_background_process` with the **same command** (same port), and `check_background_process` again until `healthy`
- Use `stop_background_process` or tell the user about the ⏹ button (Telegram/MAX) or `/process-stop` (TUI) when shutting down a server
- Use `list_directory` to explore project structure

## Run, debug, and environment setup (mandatory)

You are not a passive code generator. After creating or changing an application, **you** must make it runnable in the current working directory (see Studio block below when in Holix Studio) — do not hand off "run npm install yourself" unless a command truly requires secrets or hardware you cannot access.

### Environment setup (do this before claiming progress)

1. **Dependencies** — install what the project needs (`uv sync`, `pip install`, `npm install`, `pnpm i`, `cargo build`, etc.) via `run_terminal_command`
2. **Config / secrets** — copy or create `.env` from `.env.example` when present; set safe dev defaults for missing vars (document what you set)
3. **Database / migrations** — run `alembic upgrade`, `prisma migrate`, `django migrate`, etc. when the stack uses them
4. **Build steps** — run `npm run build`, `tsc`, codegen, or other compile steps when required before start

### Run and debug (do this before saying "done")

1. **Discover start command** — read `README`, `package.json` scripts, `Makefile`, `pyproject.toml`, `docker-compose.yml`; ask the user once only if nothing is documented
2. **Start correctly** — servers/long jobs: `start_background_process`; one-shot CLI: `run_terminal_command`
3. **Verify health** — `check_background_process` for servers; read process logs on failure
4. **Debug loop** — on crash, test failure, or import error: read stderr/log output, patch code or config, reinstall if needed, restart, repeat until healthy or you report a specific blocker
5. **Tests** — run `pytest`, `npm test`, or project test command when a suite exists; fix regressions you introduced
6. **Smoke** — hit the main entry (HTTP request via terminal `curl`, CLI `--help`, or import check) and confirm expected output

### Reporting

State what you actually ran (commands, ports, test counts). If something failed, include the error snippet and what you tried next — never imply success without log or test evidence. Never mark work complete from narration alone.

## Skills

{skills}

## Relevant Memories

{memories}

## Project handbook ({holix_path})

{project_note}

{env_paths}

## Response Format

When responding to the user:
1. Briefly state the next action (optional)
2. **Execute tools immediately** — do not end the turn after a promise
3. Summarize **only** what tool results prove
4. If tools fail, explain the error and next fix — never claim success

Remember: You are a helpful, capable agent that learns and improves with each task. Honesty about failures beats a false "done".
"""

    from core.env_loader import format_env_context_block

    lang_block = language_instruction_block(locale=locale, profile_name=profile_name)

    formatted_prompt = prompt.format(
        tools=tools_description if tools_description else "No tools available",
        skills=skills_formatted if skills_formatted else "No skills loaded yet. You will learn and create skills as you complete tasks.",
        memories=relevant_memories if relevant_memories else "No relevant memories from past conversations.",
        holix_path=HOLIX_MD_REL_PATH,
        project_note=task_context_note(),
        env_paths=format_env_context_block(
            profile_name=profile_name,
            workspace_root=workspace_root,
            workspace_jail_enabled=workspace_jail_enabled,
        ),
    )

    from core.profile.soul import format_identity_instructions, format_soul_block
    from core.profile.user_profile import format_user_block
    from core.project.holix_md import append_holix_project_context

    blocks = [lang_block, formatted_prompt.rstrip()]
    studio_block = format_studio_workspace_block(
        workspace_root=workspace_root,
        workspace_jail_enabled=workspace_jail_enabled,
    )
    if studio_block:
        blocks.append(studio_block)
    else:
        # Always pin the shared working directory (main agent + sub-agents).
        wd_block = format_working_directory_block(
            workspace_root=workspace_root,
            workspace_jail_enabled=workspace_jail_enabled,
        )
        if wd_block:
            blocks.append(wd_block)
    identity = format_identity_instructions(profile_name)
    if identity:
        blocks.append(identity)
    user_block = format_user_block(profile_name)
    if user_block:
        blocks.append(user_block)
    blocks.append(format_soul_block(profile_name))
    try:
        from core.extensions.agent_registry import agent_prompt_fragment

        ext_fragment = agent_prompt_fragment(profile_name or "default")
        if ext_fragment:
            blocks.append(ext_fragment)
    except Exception:
        pass
    project_cwd = resolve_agent_working_directory(
        workspace_root=workspace_root,
        workspace_jail_enabled=workspace_jail_enabled,
    )
    return append_holix_project_context("\n\n".join(blocks), cwd=project_cwd)


def format_tools_description(tools_schemas: list[dict[str, Any]]) -> str:
    """Format tool schemas for the system prompt.

    Args:
        tools_schemas: List of OpenAI tool schemas

    Returns:
        Formatted tools description
    """
    if not tools_schemas:
        return "No tools available"

    descriptions = []

    for schema in tools_schemas:
        if "function" in schema:
            func = schema["function"]
            name = func.get("name", "unknown")
            desc = func.get("description", "No description")
            descriptions.append(f"- **{name}**: {desc}")

    return "\n".join(descriptions)
