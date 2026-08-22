"""UI message catalog (EN default, RU optional)."""

from __future__ import annotations

from core.i18n.locale import DEFAULT_LOCALE, normalize_locale

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "lang.current": "Interface language: {code}",
        "lang.set": "Interface language set to {code}",
        "lang.usage": "Usage: /lang en | /lang ru",
        "lang.invalid": "Unknown language: {value}. Use: en, ru",
        "lang.cmd_desc": "Switch interface language (en / ru)",
        "cleared": "Chat cleared",
        "unknown_cmd": "Unknown: {cmd}",
        "type_help": "Type /help",
        "command_failed": "Command failed: {error}",
        "streaming": "streaming {state}",
        "mode_set": "mode → {mode}",
        "usage_memory": "Usage: /memory <query>",
        "usage_switch": "Usage: /switch N",
        "usage_session_name": "Usage: /session name <name>",
        "usage_profile": "/profile <name|N>",
        "profiles_title": "Profiles",
        "invalid_profile_num": "invalid profile number",
        "unknown_profile": "unknown profile: {name}",
        "models_hint": "Models: configure agent_models in profile (holix models)",
        "memory_cleared": "memory search cleared",
        "forget.done": "Session memory cleared ({id})",
        "forget.failed": "Could not clear session memory",
        "forget.no_session": "No active session",
        "forget.not_ready": "Agent not ready",
        "copy_nothing": "nothing to copy",
        "copy_label": "copied",
        "copy_tool": "last tool output copied",
        "copy_all": "full transcript copied",
        "transcript_empty": "empty",
        "status_line": "profile {profile} · mode {mode} · session {session}",
        "metrics_error": "metrics error: {error}",
        "skill_not_assigned": "Skill /{name} is not assigned to agent '{slot}'",
        "tg.mode": "Mode: {mode}",
        "tg.streaming": "Streaming: {state}",
        "tg.subagents": "Sub-agents: {state}",
        "tg.subagents_on": "Sub-agents On",
        "tg.subagents_off": "Off",
        "tg.subagents_picker_title": "Sub-agents",
        "tg.subagents_picker_body": (
            "When off, the main agent cannot delegate work (delegate_to_subagent / plan waves)."
        ),
        "tg.subagent_watch.pick": "Sub-agents — tap one to watch live",
        "tg.subagent_watch.none": "No sub-agents in this profile.",
        "tg.subagent_watch.title": "Watching {name} [{status}] · steps {steps}",
        "tg.subagent_watch.no_steps": "No steps yet…",
        "tg.subagent_watch.stop": "⏹ Stop sub-agent",
        "tg.subagent_watch.exit": "✕ Exit watch",
        "tg.subagent_watch.closed": "Watch closed.",
        "tg.subagent_watch.gone": "Sub-agent is no longer available.",
        "tg.subagent_watch.stopped": "Sub-agent stop requested.",
        "tg.subagent_watch.busy": "Already watching another sub-agent — switched.",
        "tg.subagent_q.title": "❓ Sub-agent {name} asks:",
        "tg.subagent_q.reply_btn": "Reply to {name}",
        "tg.subagent_q.hint": "Tap the button or reply to this message.",
        "tg.subagent_q.pick": "Several sub-agents are waiting for an answer. Choose who should get it:",
        "tg.subagent_q.pick_with_text": (
            "Several sub-agents are waiting. Choose who should get this answer:"
        ),
        "tg.subagent_q.awaiting": "Next message will be sent to {name}.",
        "tg.subagent_q.sent": "Answer sent to {name}.",
        "tg.subagent_q.gone": "That sub-agent is no longer waiting.",
        "tg.subagent_q.need_text": "Send the answer as a chat message.",
        "tg.reflexion": "Reflexion: {state}",
        "tg.reflexion_on": "Reflexion On",
        "tg.reflexion_off": "Off",
        "tg.reflexion_picker_title": "Reflexion",
        "tg.reflexion_picker_body": (
            "Post-draft self-critique: the agent re-evaluates the answer and may "
            "retry. Off by default (recommended). Enabling can improve quality but "
            "may add monologue or extra latency."
        ),
        "tg.profile": "Profile: {name}",
        "tg.profile_same": "Already on profile {name}",
        "tg.profile_invalid": "Invalid profile",
        "tg.profile_current": "Current: {name}",
        "tg.profile_switch_by_key": "To switch to another profile send: /profile name access-key",
        "tg.profile_requires_key": "Profile '{name}' requires an access key: /profile name access-key",
        "tg.session": "Session: {title}{model}",
        "tg.session_switched": "Session switched",
        "tg.session_invalid": "Invalid session",
        "tg.new_session": "New session",
        "tg.tool_result": "Tool result",
        "tg.model": "Model: {label}",
        "tg.error": "Error",
        "tg.unknown_action": "Unknown action",
        "tg.no_tools": "No tool calls in this chat yet.",
        "tg.agent_not_ready": "Agent not ready",
        "tg.invalid_preset": "Invalid preset",
        "tg.invalid_provider": "Invalid provider",
        "tg.invalid_model": "Invalid model",
        "tg.cron_enabled": "Enabled: {id}",
        "tg.cron_disabled": "Disabled: {id}",
        "tg.cron_removed": "Removed: {id}",
        "tg.cron_on": "On",
        "tg.cron_off": "Off",
        "tg.cron_how_add": "How to add",
        "tg.mcp_none": "No MCP servers. Install via /mcp install first.",
        "tg.mcp_none_remove": "No MCP servers to remove.",
        "tg.menu.mode": "Mode",
        "tg.menu.profile": "Profile",
        "tg.menu.sessions": "Sessions",
        "tg.menu.streaming": "Streaming",
        "tg.menu.models": "Models",
        "tg.menu.subagents": "Sub-agents",
        "tg.menu.reflexion": "Reflexion",
        "tg.menu.pipeline": "Pipeline",
        "tg.pipeline": "Pipeline: {mode}",
        "tg.pipeline_classic": "Classic (1.0.2)",
        "tg.pipeline_modern": "Modern (anti-spam)",
        "tg.pipeline_picker_title": "Agent pipeline",
        "tg.pipeline_picker_body": (
            "Classic ≈ 1.0.2 quiet path: Reflexion/meta off, no truncation wall; "
            "still forces tools on «сделай…» so work does not stop mid-task. "
            "Modern: full anti-spam monologue honesty."
        ),
        "tg.menu.compress": "Compress context",
        "tg.menu.prev": "Prev",
        "tg.menu.next": "Next",
        "tg.help.title": "Holix — commands",
        "tg.help.chat": "Chat",
        "tg.help.chat_body": "Send text — the agent replies in one live message.",
        "tg.help.commands": "Commands (menu left of the input field):",
        "tg.help.buttons": "Buttons",
        "tg.help.buttons_body": "/mode /profile /sessions /stream — pick with buttons\n/status /menu — Sub-agents, Reflexion, models, tools\n/models — switch LLM until next message",
        "tg.help.extra": "More",
        "tg.help.extra_body": (
            "• /memory query — semantic search\n"
            "• /compress — compress chat history\n"
            "• /init — project analysis → .holix/HOLIX.md\n"
            "• /profile name — switch profile\n"
            "• /plan-confirm · /plan-reject — plan review\n"
            "• /cron — scheduled jobs\n"
            "  /cron add every day at 9 :: task\n"
            "• /spec — SDD (create / show / apply / archive)\n"
            "  /spec create id -- request · /spec apply id\n"
            "• /mcp — MCP servers menu\n"
            "  /mcp remove name — remove server\n\n"
            "Confirmations: buttons under the message or /yes /no"
        ),
        "tg.cmd.help": "Command help",
        "tg.cmd.status": "Profile, mode, session",
        "tg.cmd.models": "Switch LLM model",
        "tg.cmd.menu": "Control panel",
        "tg.cmd.mode": "Execution mode",
        "tg.cmd.profile": "Holix profile",
        "tg.cmd.stream": "Streaming on/off",
        "tg.cmd.sessions": "Session list",
        "tg.cmd.switch": "Session by number",
        "tg.cmd.clear": "Clear chat context",
        "tg.cmd.stop": "Stop running task",
        "tg.cmd.mcp": "MCP servers",
        "tg.cmd.new": "New session",
        "tg.cmd.memory": "Memory search",
        "tg.cmd.skills": "Skills list",
        "tg.cmd.subagents": "Sub-agents",
        "tg.cmd.tools": "Recent tool calls",
        "tg.cmd.last": "Last tool result",
        "tg.cmd.metrics": "Agent metrics",
        "tg.cmd.compress": "Compress context",
        "tg.cmd.forget": "Clear session memory",
        "tg.cmd.init": "Project analysis → HOLIX.md",
        "tg.cmd.cron": "Cron jobs",
        "tg.cmd.spec": "SDD: create / show / apply / archive",
        "tg.cmd.message": "Admin broadcast (all or profile)",
        "tg.message_admin_only": "Only the Telegram bot admin can use /message.",
        "tg.menu_unavailable": "This menu is not available for your account.",
        "tg.mcp_read_only": "You can view MCP servers in your profile only. Installing or changing MCP is available to the bot admin.",
        "tg.mcp_read_only_empty": "No MCP servers in your profile. Ask the bot admin to configure them.",
        "tg.message_help": (
            "<b>Admin broadcast</b>\n\n"
            "<code>/message all</code> — all approved users\n"
            "<code>/message PROFILE</code> — users mapped to a Holix profile\n"
            "<code>/message cancel</code> — cancel draft\n\n"
            "After <code>/message …</code> send the post text in the next message."
        ),
        "tg.message_cancelled": "Broadcast draft cancelled.",
        "tg.message_unknown_profile": "Unknown profile or no recipients: {name}",
        "tg.message_no_recipients": "No recipients for this broadcast.",
        "tg.message_compose_all": (
            "📝 <b>Broadcast to all</b> ({count} users)\n\n"
            "Send the post text in your next message.\n"
            "Cancel: <code>/message cancel</code>"
        ),
        "tg.message_compose_profile": (
            "📝 <b>Broadcast</b> → profile <code>{profile}</code> ({count} users)\n\n"
            "Send the post text in your next message.\n"
            "Cancel: <code>/message cancel</code>"
        ),
        "tg.cmd.yes": "Confirm action",
        "tg.cmd.no": "Deny action",
        "tg.cmd.lang": "Interface language (en / ru)",
        "tui.help.title": "Holix code UI",
        "tui.help.keys1": "  Enter — send    Shift+Enter — newline",
        "tui.help.keys2": "  {quit} — quit  {clear} — clear  {end} — bottom  Shift+Tab — mode",
        "tui.help.keys3": "  F2 or /open — copy window ({copy} copies there)",
        "tui.help.keys4": "  In chat: select text → Copy bar",
        "tui.help.macos_scroll": "  ⌃↑/⌃↓/⌃PgUp/PgDn — scroll transcript",
        "tui.help.macos_ru_kb": "  RU keyboard: ,help and .help work like /help; / = Shift+7",
        "tui.help.slash": (
            "  /help /clear /stream /mode /metrics /stop /lang\n"
            "  /copy [/tool|/all]  /open\n"
            "  /new /sessions /switch N /session name <x>\n"
            "  /profile [name|N]  /memory <q>  /last [/N]  /tools\n"
            "  /yes /no  /plan-confirm|auto|refine|reject\n"
            "  /launch [/list]  /mcp [/list|/install <key|url>|/assign|/test|/tools]\n"
            "  /spec [/init|/create|/show|/apply|/archive|/fill]\n"
            "  /commands [/reload]  — custom slash commands (.holix/commands)"
        ),
        "tui.launch.title": "External CLI launch",
        "tui.launch.assign": "Assign sub-agent",
        "tui.launch.unassign": "Unassign",
        "tui.launch.refresh": "Refresh",
        "tui.launch.close": "Close",
        "tui.launch.list_hint": "Pick a CLI · Assign opens sub-agent list · Esc back/close",
        "tui.launch.pick_subagent": "Assign to sub-agent",
        "tui.launch.pick_hint": "Select sub-agent type · Esc back to CLI list",
        "tui.launch.empty": "No external CLIs in registry.",
        "tui.launch.select_cli": "Select a CLI",
        "tui.launch.not_assigned": "not assigned",
        "tui.launch.binary_missing": "not installed",
        "tui.launch.col_subagent": "Sub-agent",
        "tui.launch.col_model": "Model slot",
        "tui.launch.col_binary": "Binary",
        "tui.launch.assigned": "Launch: {cli} → sub-agent {agent}",
        "tui.launch.unassigned": "Launch: {cli} unassigned (was {agent})",
        "tui.launch.unsupported": "holix launch is available only on Linux and macOS.",
        "tui.launch.error": "Launch manager: {error}",
        "tui.launch.cli_hint": "Use: holix launch setup (terminal) or /launch in TUI on Linux/macOS",
        "tui.launch.list_footer": "Change assignments: /launch",
        "tui.launch.usage": (
            "Usage: /launch · /launch list · /launch sessions · "
            "/launch claude [-t task] · /launch claude restart · "
            "/launch send <id> <text> · /launch output <id>"
        ),
        "tui.launch.start": "Launch",
        "tui.launch.restart_btn": "Restart",
        "tui.launch.started": "Launched {cli} in tmux {session} (id={sid})",
        "tui.launch.restarted": "Restarted {cli} in tmux {session} (id={sid})",
        "tui.launch.no_sessions": "No active external CLI sessions.",
        "tui.launch.sessions_title": "Active launch sessions",
        "tui.launch.sessions_footer": "Send: /launch send <id> <prompt> · Output: /launch output <id>",
        "tui.launch.sent": "Sent prompt to session {session}",
        "tui.launch.killed": "Stopped session {session}",
        "tui.launch.output_empty": "(empty pane)",
        "tui.launch.task": "Task",
        "tui.launch.followup": "Follow-up: /launch send {id} … · output: /launch output {id}",
        "tui.launch.parse_error": "Could not parse /launch command: {error}",
        "tui.process.title": "Background process",
        "tui.process.hint": "Latest log output · Refresh to update · Kill stops the process",
        "tui.process.refresh": "Refresh",
        "tui.process.kill": "Kill",
        "tui.process.close": "Close",
        "tui.process.command": "Command",
        "tui.process.not_found": "No background process for this session.",
        "tui.process.output_empty": "(no log output yet)",
        "tui.process.output_waiting": "(process is running — waiting for log output)",
        "tui.process.status_running": "running",
        "tui.process.status_stopped": "stopped",
        "tui.process.already_stopped": "Process is already stopped.",
        "tui.process.killed": "[dim]⏹ stopped: {label} (pid {pid})[/dim]",
        "tui.process.killed_short": "Stopped {label}",
        "tui.subagent_types.title": "Sub-agent types",
        "tui.subagent_types.create": "Create type",
        "tui.subagent_types.edit": "Edit",
        "tui.subagent_types.delete": "Delete",
        "tui.subagent_types.save": "Save",
        "tui.subagent_types.cancel": "Cancel",
        "tui.subagent_types.refresh": "Refresh",
        "tui.subagent_types.close": "Close",
        "tui.subagent_types.list_hint": "Built-in types are read-only · Create custom types with prompt, skills, MCP, model, CLI",
        "tui.subagent_types.form_title": "Custom sub-agent type",
        "tui.subagent_types.form_hint": "Name (slug) · system prompt · tools · skills · MCP · model · external CLI",
        "tui.subagent_types.tools": "Tools",
        "tui.subagent_types.skills": "Skills (allowlist for this type)",
        "tui.subagent_types.mcp": "MCP servers",
        "tui.subagent_types.model": "Model slot",
        "tui.subagent_types.external_cli": "External CLI (holix launch)",
        "tui.subagent_types.builtin": "built-in",
        "tui.subagent_types.custom": "custom",
        "tui.subagent_types.empty": "No sub-agent types found.",
        "tui.subagent_types.select_type": "Select a type · built-in types cannot be edited here",
        "tui.subagent_types.builtin_readonly": "Built-in types are defined in code and cannot be edited in TUI.",
        "tui.subagent_types.not_found": "Custom type not found.",
        "tui.subagent_types.prompt_required": "System prompt is required.",
        "tui.subagent_types.saved": "Saved sub-agent type: {name}",
        "tui.subagent_types.deleted": "Deleted sub-agent type: {name}",
        "tui.subagent_types.error": "Sub-agent types manager: {error}",
        "tui.subagent_types.cli_hint": "Use /subagent-types in TUI to create custom sub-agent types.",
        "tui.subagent_types.list_footer": "Manage types: /subagent-types",
        "tui.subagent_types.usage": "Usage: /subagent-types · /subagent-types list",
        "init.ack": "▸ /init — project analysis → {path} (mode: {mode})",
        "init.ack_scoped": "▸ /init — project analysis → {path} in `{dir}/` (mode: {mode})",
        "init.scope_dir": (
            "**Project scope:** analyze only the `{dir}/` directory (relative to workspace root). "
            "Treat it as the project root for this onboarding. "
            "Do not scan sibling directories unless needed for context."
        ),
        "init.busy": ("Agent is busy with a previous request. Wait for the reply or send /stop."),
        "init.not_ready": "Agent not ready. Configure a model first (holix models add).",
        "init.large_hint": (
            "This is a **large repository**. Follow the read budget strictly — "
            "completeness comes from scoped `/init <subdir>` runs on subprojects, "
            "not one exhaustive pass."
        ),
        "init.scan.header": "## Pre-scan (automated)",
        "init.scan.scope": "Scope: `{dir}` — ~{files} files (vendor/cache dirs excluded).",
        "init.scan.large_flag": (
            "**Large repository** — use the budget rules below; do not rescan the whole tree."
        ),
        "init.scan.top_dirs": "Top-level directories: {dirs}",
        "init.scan.subprojects": "Detected subprojects (scoped `/init` targets):\n{items}",
        "init.scan.manifests": "Package / build manifests:",
        "init.scan.readmes": "README / contributing files:",
        "init.scan.doc_dirs": "Documentation directories: {dirs}",
        "init.scan.extensions": "File types (sample): {summary}",
        "init.scan.tree": "Directory tree (truncated):",
        "init.scan.subprojects_heading": "Subprojects",
        "init.scan.skeleton_note": "Auto-generated skeleton from /init pre-scan — fill gaps below",
        "init.scan.prefill_heading": "Pre-filled from scan",
        "init.scan.prefill_files": "Approx. {count} source files in scope",
        "init.scan.prefill_scope": "Scope directory: `{dir}`",
        "init.scan.tree_heading": "Directory tree",
        "init.holix_template": """# Project context (Holix)

> Generated by `/init`. Update when the codebase changes significantly.

## Overview
- Purpose:
- Primary users / consumers:
- Repository type (monorepo, service, library, …):

## Directory structure
```
(tree — annotate important folders)
```

## Technology stack
- Languages:
- Frameworks:
- Databases / queues / caches:
- Package managers & build tools:

## Architecture
- High-level diagram (text or mermaid):
- Main layers / bounded contexts:
- Entry points (CLI, HTTP, workers, …):

## REST / HTTP API (if applicable)
- Base URL / versioning:
- Auth:
- Route map (method, path, handler/module, purpose):
- Request/response patterns:

## Key modules & responsibilities
| Module / package | Role |
|------------------|------|

## Configuration & environment
- Config files:
- Required env vars:
- Secrets handling:

## Documentation index
| Path | What it describes |
|------|-------------------|

## Development workflow
- Install:
- Run locally:
- Test:
- Lint / format:

## Code conventions
- Style / lint rules:
- Naming patterns:
- Error handling / logging:
- Testing approach:

## Important files
| File | Why it matters |

## Notes & gotchas
- …""",
        "init.user_message": """Run **project onboarding** for the current working directory.

## Goal
Produce an accurate project handbook at **`{path}`**. A **skeleton file already exists** at that path with pre-scan data — **edit and extend it**, do not start from scratch.
Every future agent in this repo will rely on this file first.

## Pre-scan report (do not repeat this discovery)
{scan_report}

## How to work
1. **Read the existing `{path}` first** — it already contains the directory tree, manifest list, and template sections.
2. **Budget:** at most **~20 `read_file` calls** total. Prioritize: root README, manifests from the pre-scan list, one representative file per major package, API specs if any.
3. Do **not** run broad recursive `list_directory` or repo-wide `find`/`tree` — the pre-scan already mapped the layout.
4. Use `run_terminal_command` only for quick, bounded checks (e.g. `head`, `rg -l` with limits) when a manifest points to scripts.
5. For **monorepos** (multiple subprojects in pre-scan): document repo-level overview here; list each subproject with 2–3 sentences; note that scoped `/init <path>` can deepen each package later. Do **not** read every subproject in one run.
6. Fill template sections with **specific facts** from files you read; mark unknowns as "TBD" rather than guessing.
7. Update **`{path}` with `update_holix_section`** — **one section per call** (heading + body under ~30 lines). This is the primary tool for /init.
8. Use **`patch_file` only** for tiny placeholder tweaks (1–3 replacements, each `new_string` under 15 lines). **Never** call `write_file` on HOLIX.md.
9. **Do not** write narrative like «creating the handbook» — call `update_holix_section` immediately, then continue to the next section.

## Output
- Finalize **`{path}`** via multiple **`update_holix_section`** calls (preserve pre-filled tree and subproject table).
- **Forbidden:** `write_file` on `{path}`, large `patch_file` payloads, or dumping the full handbook in assistant text.
- Use the structure below (fill every section; add subsections as needed).
- Be **specific** (file paths, module names, command examples from real configs).
- Do **not** skip API or data-layer documentation if the project has them.
- Write the entire handbook in **English** (headings, descriptions, tables).

## Required template
```markdown
{template}
```

When finished, confirm the absolute path written and give a 5–10 line summary of what you captured.""",
        "prompt.lang_block": (
            "## Language\n"
            "The user set the interface language to English (`/lang en`).\n"
            "**You MUST write ALL user-visible text only in English** — final answers, "
            "intermediate plans, step lists, analysis, summaries, clarifying questions, "
            "and commentary before/after tool calls — even if the user writes in another "
            "language.\n"
            "Never expose internal chain-of-thought or reasoning traces as your only reply; "
            "always provide a proper user-facing answer in English.\n"
            "For status questions (what you are doing, open tasks, progress): call "
            "`list_subagents()` when needed, then answer in plain language what you are doing "
            "now and which tasks are pending.\n"
            "Exception: switch language only if the user explicitly asks for a different "
            "language in that specific message."
        ),
        "llm.truncated": (
            "Response truncated by the model token limit. "
            "I stopped instead of repeating myself — ask me to continue, "
            "or rephrase more narrowly / use a model with a larger output budget."
        ),
        "llm.content_filter": "The model rejected the request (content filter).",
        "llm.reasoning_only": (
            "The model finished reasoning without a visible answer. Please try again."
        ),
        "work_status.title": "**Work status**",
        "work_status.main_label": "**Main agent:** {state}",
        "work_status.main_idle": "idle — ready for your request",
        "work_status.main_busy": "processing a request",
        "work_status.tasks_label": "**Open tasks:**",
        "work_status.tasks_unknown": "- (no task recorded in this session yet)",
        "work_status.last_action_label": "**Last action:**",
        "work_status.action_unknown": "(no recent assistant reply)",
        "work_status.subagents_disabled": "**Sub-agents:** disabled in profile",
        "work_status.subagents_empty": (
            "**Sub-agents:** none running.\nTo start one: `/subagent-spawn coder <task>`"
        ),
        "work_status.subagents_header": "**Sub-agents:** {total} total (running: {running})",
        "work_status.subagent_line": "• `{name}` — {status}{preview}",
        "live.thinking": "Thinking…",
        "live.working": "Working…",
        "live.reasoning": "Model is reasoning…",
        "live.thinking_step": "Thinking (step {step})…",
        "live.holix_thinking": "Holix is thinking… (mode: {mode})",
        "live.processing": "Holix is processing your request…",
        "live.still_working": "Holix is still working…",
        "live.generating_plan": "Generating execution plan (timeout: {timeout}s)…",
        "live.plan_review": "⏸ Plan review ({count} steps)",
        "live.answer_sent": "Answer sent as a separate message ↓",
        "live.bg_process_started": "🟢 Background process running\n<code>{label}</code>",
        "live.bg_process_stopped": "⏹ Background process stopped\n<code>{label}</code>",
        "live.bg_process_error": "⚠ Background process error\n<code>{label}</code>\n{summary}",
        "live.plan.phase_start": "📋 Plan mode: preparing to build an execution plan…",
        "live.plan.phase_context": "📋 Collecting memory & tools context ({memories} memories, {tools} tools)…",
        "live.plan.phase_handbook": "📋 Loading project handbook / specs (workspace: {path})…",
        "live.plan.phase_handbook_init": "📋 Handbook missing — running /init pre-scan…",
        "live.plan.phase_llm": "📋 Asking the model to design the plan (model: {model}, timeout: {timeout}s)…",
        "live.plan.phase_llm_wait": "📋 Model is still generating the plan… {elapsed}s elapsed (timeout {timeout}s)",
        "live.plan.phase_attempt": "📋 Plan generation attempt {attempt}/{total}…",
        "live.plan.phase_received": "📋 Plan draft received ({chars} chars) — parsing…",
        "live.plan.phase_quality": "📋 Checking plan quality (steps, report completeness)…",
        "live.plan.phase_retry": "📋 Plan not solid enough — refining with the model ({reason})…",
        "live.plan.phase_save": "📋 Saving draft plan ({steps} steps) for your review…",
        "live.plan.phase_ready": "📋 Plan ready: {steps} steps — waiting for your approval",
        "live.plan.phase_waiting_review": "⏸ Waiting for you to approve or refine the plan ({steps} steps)…",
        "plan.title": "📋 Execution Plan — {count} steps",
        "plan.task_label": "Task:",
        "plan.analysis": "📊 Analysis",
        "plan.summary": "Summary:",
        "plan.complexity": "Complexity:",
        "plan.questions": "❓ Clarifying Questions",
        "plan.questions_hint": "Describe what you'd like to change to answer these questions.",
        "plan.constraints": "🔒 Constraints",
        "plan.architecture": "🏗️ Architecture",
        "plan.approach": "Approach:",
        "plan.tech_stack": "Tech Stack:",
        "plan.structure": "Structure:",
        "plan.risks": "⚡ Risks & Mitigations",
        "plan.risk_col": "Risk",
        "plan.mitigation_col": "Mitigation",
        "plan.steps": "📝 Execution Steps",
        "plan.step": "Step {num}",
        "plan.step_in_progress": "in progress",
        "plan.step_failed": "failed",
        "plan.tools": "Tools:",
        "plan.subagent": "Sub-agent:",
        "plan.parallel": "Parallel group:",
        "plan.depends": "Depends on:",
        "plan.expected": "Expected output:",
        "plan.success": "Success criteria:",
        "plan.reasoning": "💭 Reasoning",
        "plan.no_description": "No description",
        "plan.refine_hint": "_Or reply with text to refine the plan._",
        "plan.approval_hint": "_Reply **yes** to start development, **no** to cancel, or describe changes to refine the plan._",
        "plan.clarify.title": "❓ Clarification needed before planning",
        "plan.clarify.reason": "Why clarification is needed:",
        "plan.clarify.questions": "Questions",
        "plan.clarify.hint": "_Answer the questions above. Reply **proceed with assumptions** to skip, or **no** to cancel._",
        "plan.clarify.default_question": "Please clarify the requirements for this task.",
        "plan.clarify.rejected": "Planning cancelled. Ask again when you're ready to provide more detail.",
        "plan.report.default_title": "Development Plan",
        "plan.report.section_summary": "1. Executive Summary",
        "plan.report.goal": "Goal:",
        "plan.report.key_decisions": "Key decisions:",
        "plan.report.critical_risks": "Critical risks:",
        "plan.report.section_stages": "2. Development Stages",
        "plan.report.stage": "Stage {num}",
        "plan.report.duration": "Estimated duration:",
        "plan.report.section_priorities": "3. Priorities",
        "plan.report.priority_mvp": "Critical for MVP (blocks launch)",
        "plan.report.priority_later": "Important, can defer 1–2 iterations",
        "plan.report.priority_optional": "Optional / future",
        "plan.report.section_dependencies": "4. Task Dependencies",
        "plan.report.dep_task": "Task",
        "plan.report.dep_depends": "Depends on",
        "plan.report.dep_unblocks": "Unblocks",
        "plan.report.parallel_work": "Parallel work possible:",
        "plan.report.section_blockers": "5. Blockers & Risks",
        "plan.report.blocker_risk": "Risk",
        "plan.report.blocker_probability": "Probability",
        "plan.report.blocker_impact": "Impact",
        "plan.report.blocker_mitigation": "Mitigation",
        "plan.report.section_manual": "6. Manual Actions",
        "plan.report.manual_action": "Action",
        "plan.report.manual_when": "When",
        "plan.report.manual_who": "Who",
        "plan.report.section_estimates": "7. Time & Cost Estimate",
        "plan.report.estimate_stage": "Stage",
        "plan.report.estimate_hours": "Hours",
        "plan.report.estimate_sp": "Story Points",
        "plan.report.total": "Total:",
        "plan.report.hours_unit": "hours",
        "plan.report.calendar": "Calendar time:",
        "plan.report.buffer": "Buffer:",
        "plan.report.section_stack": "8. Recommended Stack & Architecture",
        "plan.report.stack_tech": "Technology stack",
        "plan.report.stack_patterns": "Architectural patterns",
        "plan.report.stack_fixes": "Critical architectural fixes (vs original spec)",
        "studio.wait_for_run": "Wait for the reply or press Stop.",
        "studio.timeout": "Execution timed out. Try again or use /models.",
        "supervisor.repeating": "Repeating: {target}",
        "supervisor.last_result": "Last result: {result}",
        "supervisor.stuck": "What is stuck: {problem}",
        "supervisor.tool": "Tool: {tool}",
        "supervisor.known": "Already known: {known}",
        "supervisor.last_tool_result": "Last tool result: {result}",
        "supervisor.asked_agent": "What the supervisor already asked the agent to do: {next}",
        "supervisor.fallback_q": (
            "Sub-agent `{name}` is stuck in a tool loop ({summary}). "
            "What should it do next, or should it stop?"
        ),
        "supervisor.q.inspect": (
            "The coder is stuck inspecting libraries instead of writing files{target}. "
            "Should it implement from known FastAPI/Dishka APIs, skip this step, "
            "or do you want a different approach?"
        ),
        "supervisor.q.noop_write": (
            "The coder keeps rewriting files that already match disk{target}. "
            "Should it stop and finalize, run tests once, or change a specific file?"
        ),
        "supervisor.q.launch": (
            "The coder keeps launching the server in terminal instead of "
            "start_background_process{target}. "
            "Should it switch to the background tool, skip the server, or stop?"
        ),
        "supervisor.q.venv": (
            "The coder is looping on `ls/grep` inside .venv{target}. "
            "Those packages are not installed. Should it implement without them, "
            "`uv add` a specific package, or stop and wait for you?"
        ),
        "supervisor.q.install": (
            "The coder is retrying the same install command{target}. "
            "Should it continue with current deps, install a named package, or stop?"
        ),
        "supervisor.q.terminal": (
            "The coder is repeating the same terminal command{target}. "
            "What should it do instead (which file to edit, which command, or stop)?"
        ),
        "supervisor.q.read": (
            "The coder keeps re-reading the same file{target}. "
            "Which change should it make, or should it stop?"
        ),
        "supervisor.q.search": (
            "The coder is stuck repeating grep/glob{target}. "
            "Which path should it open, or should it stop searching?"
        ),
        "supervisor.q.write": (
            "The coder keeps rewriting the same file{target}. "
            "Should it finalize, edit a different file, or stop?"
        ),
        "supervisor.q.web": (
            "The coder is looping on web_search/web_fetch{target}. "
            "Should it write from current evidence, try a specific URL, or stop?"
        ),
        "supervisor.q.generic": (
            "The coder is looping on `{tool}`{target}. What should it do next, or should it stop?"
        ),
        "supervisor.p.inspect": "library introspection via terminal",
        "supervisor.p.noop_write": "rewriting files that already match disk",
        "supervisor.p.launch": "starting a long-running server in the foreground terminal",
        "supervisor.p.venv": "searching the virtualenv for missing packages",
        "supervisor.p.install": "repeating a package-install command",
        "supervisor.p.terminal": "repeating the same `{tool}` command",
        "supervisor.p.read": "re-reading the same file",
        "supervisor.p.search": "repeating the same search",
        "supervisor.p.write": "rewriting the same file",
        "supervisor.p.web": "repeating the same web search/fetch",
        "supervisor.p.generic": "repeating `{tool}`",
        "supervisor.k.inspect": "inspect/python -c on third-party packages will not write the project.",
        "supervisor.k.noop_write": "write_file already reported no content changes.",
        "supervisor.k.launch": "foreground uvicorn/npm/etc. blocks the agent and is not how Studio tracks processes.",
        "supervisor.k.venv_absent": "The venv listing already shows those packages are not installed. Repeating ls/grep will not install them.",
        "supervisor.k.venv": "Hunting site-packages does not implement the task.",
        "supervisor.k.install": "the install command already ran; retrying it is not progress.",
        "supervisor.k.terminal_result": "The last command already returned an answer (including empty / not found).",
        "supervisor.k.terminal": "Repeating the same shell command will not change the result.",
        "supervisor.k.read": "you already have this file contents.",
        "supervisor.k.search": "the search already returned its hits (or none).",
        "supervisor.k.write": "another rewrite of the same path is not new work.",
        "supervisor.k.web": "you already have that page/query result.",
        "supervisor.k.generic": "the same tool call will not produce new information.",
        "skill.notice.pending": "New skill proposed: {name}",
        "skill.notice.auto": "New skill auto-accepted: {name}",
        "skill.notice.score": "Quality {score}/100 · {tier} — {hint}",
        "skill.notice.actions": "Approve or reject below, or open Settings → Skills.",
        "skill.btn.approve": "Approve",
        "skill.btn.reject": "Reject",
        "skill.cb.approved": "Skill approved",
        "skill.cb.rejected": "Skill rejected",
        "skill.cb.missing": "Proposal not found (already decided?)",
        "skill.cb.error": "Could not apply: {error}",
    },
    "ru": {
        "lang.current": "Язык интерфейса: {code}",
        "lang.set": "Язык интерфейса: {code}",
        "lang.usage": "Использование: /lang en | /lang ru",
        "lang.invalid": "Неизвестный язык: {value}. Доступно: en, ru",
        "lang.cmd_desc": "Сменить язык интерфейса (en / ru)",
        "cleared": "Чат очищен",
        "unknown_cmd": "Неизвестная команда: {cmd}",
        "type_help": "Введите /help",
        "command_failed": "Ошибка команды: {error}",
        "streaming": "стриминг {state}",
        "mode_set": "режим → {mode}",
        "usage_memory": "Использование: /memory <запрос>",
        "usage_switch": "Использование: /switch N",
        "usage_session_name": "Использование: /session name <имя>",
        "usage_profile": "/profile <имя|N>",
        "profiles_title": "Профили",
        "invalid_profile_num": "неверный номер профиля",
        "unknown_profile": "неизвестный профиль: {name}",
        "models_hint": "Модели: настройте agent_models в профиле (holix models)",
        "memory_cleared": "поиск в памяти сброшен",
        "forget.done": "Память сессии очищена ({id})",
        "forget.failed": "Не удалось очистить память сессии",
        "forget.no_session": "Нет активной сессии",
        "forget.not_ready": "Агент не готов",
        "copy_nothing": "нечего копировать",
        "copy_label": "скопировано",
        "copy_tool": "результат tool скопирован",
        "copy_all": "весь транскрипт скопирован",
        "transcript_empty": "пусто",
        "status_line": "профиль {profile} · режим {mode} · сессия {session}",
        "metrics_error": "ошибка метрик: {error}",
        "skill_not_assigned": "Навык /{name} не назначен агенту '{slot}'",
        "tg.mode": "Режим: {mode}",
        "tg.streaming": "Стриминг: {state}",
        "tg.subagents": "Субагенты: {state}",
        "tg.subagents_on": "Субагенты Вкл",
        "tg.subagents_off": "Выкл",
        "tg.subagents_picker_title": "Субагенты",
        "tg.subagents_picker_body": (
            "Когда выключено, главный агент не может делегировать задачи "
            "(delegate_to_subagent / волны в plan)."
        ),
        "tg.subagent_watch.pick": "Субагенты — нажмите, чтобы смотреть вживую",
        "tg.subagent_watch.none": "В этом профиле нет субагентов.",
        "tg.subagent_watch.title": "Просмотр {name} [{status}] · шаги {steps}",
        "tg.subagent_watch.no_steps": "Шагов пока нет…",
        "tg.subagent_watch.stop": "⏹ Остановить субагента",
        "tg.subagent_watch.exit": "✕ Выйти из просмотра",
        "tg.subagent_watch.closed": "Просмотр закрыт.",
        "tg.subagent_watch.gone": "Субагент больше недоступен.",
        "tg.subagent_watch.stopped": "Остановка субагента запрошена.",
        "tg.subagent_watch.busy": "Уже смотрите другого субагента — переключили.",
        "tg.subagent_q.title": "❓ Субагент {name} спрашивает:",
        "tg.subagent_q.reply_btn": "Ответить {name}",
        "tg.subagent_q.hint": "Нажмите кнопку или ответьте на это сообщение.",
        "tg.subagent_q.pick": "Несколько субагентов ждут ответ. Выберите, кому отправить:",
        "tg.subagent_q.pick_with_text": (
            "Несколько субагентов ждут ответ. Выберите, кому отправить этот текст:"
        ),
        "tg.subagent_q.awaiting": "Следующее сообщение уйдёт субагенту {name}.",
        "tg.subagent_q.sent": "Ответ отправлен субагенту {name}.",
        "tg.subagent_q.gone": "Этот субагент уже не ждёт ответ.",
        "tg.subagent_q.need_text": "Напишите ответ сообщением в чат.",
        "tg.reflexion": "Reflexion: {state}",
        "tg.reflexion_on": "Reflexion Вкл",
        "tg.reflexion_off": "Выкл",
        "tg.reflexion_picker_title": "Reflexion",
        "tg.reflexion_picker_body": (
            "Самокритика после черновика: агент оценивает ответ и может "
            "переписать. По умолчанию выкл (рекомендуется). Включение может "
            "улучшить качество, но иногда даёт монологи и лишнюю задержку."
        ),
        "tg.profile": "Профиль: {name}",
        "tg.profile_same": "Уже профиль {name}",
        "tg.profile_invalid": "Неверный профиль",
        "tg.profile_current": "Сейчас: {name}",
        "tg.profile_switch_by_key": "Для переключения на другой профиль: /profile имя ключ",
        "tg.profile_requires_key": "Профиль «{name}» требует ключ: /profile имя ключ",
        "tg.session": "Сессия: {title}{model}",
        "tg.session_switched": "Сессия переключена",
        "tg.session_invalid": "Неверная сессия",
        "tg.new_session": "Новая сессия",
        "tg.tool_result": "Результат tool",
        "tg.model": "Модель: {label}",
        "tg.error": "Ошибка",
        "tg.unknown_action": "Неизвестное действие",
        "tg.no_tools": "Пока нет вызовов tools в этом чате.",
        "tg.agent_not_ready": "Агент не готов",
        "tg.invalid_preset": "Неверный пресет",
        "tg.invalid_provider": "Неверный провайдер",
        "tg.invalid_model": "Неверная модель",
        "tg.cron_enabled": "Включено: {id}",
        "tg.cron_disabled": "Выключено: {id}",
        "tg.cron_removed": "Удалено: {id}",
        "tg.cron_on": "Вкл",
        "tg.cron_off": "Выкл",
        "tg.cron_how_add": "Как добавить",
        "tg.mcp_none": "Нет MCP серверов. Сначала установи через /mcp install.",
        "tg.mcp_none_remove": "Нет MCP серверов для удаления.",
        "tg.menu.mode": "Режим",
        "tg.menu.profile": "Профиль",
        "tg.menu.sessions": "Сессии",
        "tg.menu.streaming": "Стриминг",
        "tg.menu.models": "Модели",
        "tg.menu.subagents": "Субагенты",
        "tg.menu.reflexion": "Reflexion",
        "tg.menu.pipeline": "Pipeline",
        "tg.pipeline": "Pipeline: {mode}",
        "tg.pipeline_classic": "Classic (1.0.2)",
        "tg.pipeline_modern": "Modern (anti-spam)",
        "tg.pipeline_picker_title": "Pipeline агента",
        "tg.pipeline_picker_body": (
            "Classic ≈ 1.0.2: тихо (без Reflexion/meta и «обрезан…»), но на "
            "«сделай…» tools обязательны — не останавливается на полпути. "
            "Modern: полный anti-spam honesty."
        ),
        "tg.menu.compress": "Сжать контекст",
        "tg.menu.prev": "Пред.",
        "tg.menu.next": "След.",
        "tg.help.title": "Holix — команды",
        "tg.help.chat": "Чат",
        "tg.help.chat_body": "Отправьте текст — агент ответит одним живым сообщением.",
        "tg.help.commands": "Команды (меню слева от поля ввода):",
        "tg.help.buttons": "Кнопки",
        "tg.help.buttons_body": "/mode /profile /sessions /stream — выбор кнопками\n/status /menu — субагенты, Reflexion, модели, tools\n/models — смена LLM до следующего сообщения",
        "tg.help.extra": "Дополнительно",
        "tg.help.extra_body": (
            "• /memory запрос — семантический поиск\n"
            "• /compress — сжать историю диалога\n"
            "• /init — анализ проекта в .holix/HOLIX.md\n"
            "• /profile имя — смена профиля\n"
            "• /plan-confirm · /plan-reject — план\n"
            "• /cron — периодические задачи\n"
            "  /cron add every day at 9 :: задача\n"
            "• /spec — SDD (создать / смотреть / apply / архив)\n"
            "  /spec create id -- запрос · /spec apply id\n"
            "• /mcp — меню MCP серверов\n"
            "  /mcp remove имя — удалить сервер\n\n"
            "Подтверждения: кнопки под сообщением или /yes /no"
        ),
        "tg.cmd.help": "Справка по командам",
        "tg.cmd.status": "Профиль, режим, сессия",
        "tg.cmd.models": "Сменить LLM модель",
        "tg.cmd.menu": "Панель управления",
        "tg.cmd.mode": "Режим выполнения",
        "tg.cmd.profile": "Профиль Holix",
        "tg.cmd.stream": "Стриминг вкл/выкл",
        "tg.cmd.sessions": "Список сессий",
        "tg.cmd.switch": "Сессия по номеру",
        "tg.cmd.clear": "Очистить контекст чата",
        "tg.cmd.stop": "Остановить задачу",
        "tg.cmd.mcp": "MCP серверы",
        "tg.cmd.new": "Новая сессия",
        "tg.cmd.memory": "Поиск в памяти",
        "tg.cmd.skills": "Список навыков",
        "tg.cmd.subagents": "Субагенты",
        "tg.cmd.tools": "Последние вызовы tools",
        "tg.cmd.last": "Последний результат tool",
        "tg.cmd.metrics": "Метрики агента",
        "tg.cmd.compress": "Сжать контекст",
        "tg.cmd.forget": "Очистить память сессии",
        "tg.cmd.init": "Анализ проекта → HOLIX.md",
        "tg.cmd.cron": "Периодические задачи",
        "tg.cmd.spec": "SDD: создать / смотреть / apply / архив",
        "tg.cmd.message": "Рассылка админа (всем или профилю)",
        "tg.message_admin_only": "Команда /message доступна только администратору бота.",
        "tg.menu_unavailable": "Это меню недоступно для вашей учётной записи.",
        "tg.mcp_read_only": "Доступен только просмотр MCP вашего профиля. Установка и изменение — у администратора бота.",
        "tg.mcp_read_only_empty": "В вашем профиле нет MCP серверов. Попросите администратора бота настроить их.",
        "tg.message_help": (
            "<b>Рассылка администратора</b>\n\n"
            "<code>/message all</code> — всем одобренным пользователям\n"
            "<code>/message ПРОФИЛЬ</code> — пользователям Holix-профиля\n"
            "<code>/message cancel</code> — отменить черновик\n\n"
            "После <code>/message …</code> отправьте текст поста следующим сообщением."
        ),
        "tg.message_cancelled": "Черновик рассылки отменён.",
        "tg.message_unknown_profile": "Профиль не найден или нет получателей: {name}",
        "tg.message_no_recipients": "Нет получателей для рассылки.",
        "tg.message_compose_all": (
            "📝 <b>Рассылка всем</b> ({count} чел.)\n\n"
            "Отправьте текст поста следующим сообщением.\n"
            "Отмена: <code>/message cancel</code>"
        ),
        "tg.message_compose_profile": (
            "📝 <b>Рассылка</b> → профиль <code>{profile}</code> ({count} чел.)\n\n"
            "Отправьте текст поста следующим сообщением.\n"
            "Отмена: <code>/message cancel</code>"
        ),
        "tg.cmd.yes": "Подтвердить действие",
        "tg.cmd.no": "Отклонить действие",
        "tg.cmd.lang": "Язык интерфейса (en / ru)",
        "tui.help.title": "Holix code UI",
        "tui.help.keys1": "  Enter — отправить    Shift+Enter — новая строка",
        "tui.help.keys2": "  {quit} — выход  {clear} — очистить  {end} — вниз  Shift+Tab — режим",
        "tui.help.keys3": "  F2 или /open — окно копирования ({copy})",
        "tui.help.keys4": "  В чате: выделите текст → панель Copy",
        "tui.help.macos_scroll": "  ⌃↑/⌃↓/⌃PgUp/PgDn — прокрутка транскрипта",
        "tui.help.macos_ru_kb": "  Русская раскладка: ,help и .help как /help; / = Shift+7",
        "tui.help.slash": (
            "  /help /clear /stream /mode /metrics /stop /lang\n"
            "  /copy [/tool|/all]  /open\n"
            "  /new /sessions /switch N /session name <имя>\n"
            "  /profile [имя|N]  /memory <запрос>  /last [/N]  /tools\n"
            "  /yes /no  /plan-confirm|auto|refine|reject\n"
            "  /launch [/list]  /mcp [/list|/install <key|url>|/assign|/test|/tools]\n"
            "  /spec [/init|/create|/show|/apply|/archive|/fill]\n"
            "  /commands [/reload]  — пользовательские slash-команды (.holix/commands)"
        ),
        "tui.launch.title": "Внешние CLI (launch)",
        "tui.launch.assign": "Назначить субагента",
        "tui.launch.unassign": "Снять назначение",
        "tui.launch.refresh": "Обновить",
        "tui.launch.close": "Закрыть",
        "tui.launch.list_hint": "Выберите CLI · «Назначить» — список субагентов · Esc назад/закрыть",
        "tui.launch.pick_subagent": "Назначить субагенту",
        "tui.launch.pick_hint": "Выберите тип субагента · Esc — к списку CLI",
        "tui.launch.empty": "Нет внешних CLI в реестре.",
        "tui.launch.select_cli": "Выберите CLI",
        "tui.launch.not_assigned": "не назначен",
        "tui.launch.binary_missing": "не установлен",
        "tui.launch.col_subagent": "Субагент",
        "tui.launch.col_model": "Слот модели",
        "tui.launch.col_binary": "Бинарник",
        "tui.launch.assigned": "Launch: {cli} → субагент {agent}",
        "tui.launch.unassigned": "Launch: {cli} — назначение снято (был {agent})",
        "tui.launch.unsupported": "holix launch доступен только на Linux и macOS.",
        "tui.launch.error": "Менеджер launch: {error}",
        "tui.launch.cli_hint": "Терминал: holix launch setup · TUI (Linux/macOS): /launch",
        "tui.launch.list_footer": "Изменить назначения: /launch",
        "tui.launch.usage": (
            "Использование: /launch · /launch list · /launch sessions · "
            "/launch claude [-t задача] · /launch claude restart · "
            "/launch send <id> <текст> · /launch output <id>"
        ),
        "tui.launch.start": "Запустить",
        "tui.launch.restart_btn": "Перезапуск",
        "tui.launch.started": "Запущен {cli} в tmux {session} (id={sid})",
        "tui.launch.restarted": "Перезапущен {cli} в tmux {session} (id={sid})",
        "tui.launch.no_sessions": "Нет активных сессий внешних CLI.",
        "tui.launch.sessions_title": "Активные launch-сессии",
        "tui.launch.sessions_footer": "Отправить: /launch send <id> <запрос> · Вывод: /launch output <id>",
        "tui.launch.sent": "Запрос отправлен в сессию {session}",
        "tui.launch.killed": "Сессия остановлена: {session}",
        "tui.launch.output_empty": "(пустая панель)",
        "tui.launch.task": "Задача",
        "tui.launch.followup": "Дальше: /launch send {id} … · вывод: /launch output {id}",
        "tui.launch.parse_error": "Не удалось разобрать /launch: {error}",
        "tui.process.title": "Фоновый процесс",
        "tui.process.hint": "Последний вывод лога · Обновить — перечитать · Убить — остановить процесс",
        "tui.process.refresh": "Обновить",
        "tui.process.kill": "Убить",
        "tui.process.close": "Закрыть",
        "tui.process.command": "Команда",
        "tui.process.not_found": "Нет фонового процесса для этой сессии.",
        "tui.process.output_empty": "(вывод лога пока пуст)",
        "tui.process.output_waiting": "(процесс запущен — ждём вывод в лог)",
        "tui.process.status_running": "работает",
        "tui.process.status_stopped": "остановлен",
        "tui.process.already_stopped": "Процесс уже остановлен.",
        "tui.process.killed": "[dim]⏹ остановлен: {label} (pid {pid})[/dim]",
        "tui.process.killed_short": "Остановлен: {label}",
        "tui.subagent_types.title": "Типы субагентов",
        "tui.subagent_types.create": "Создать тип",
        "tui.subagent_types.edit": "Изменить",
        "tui.subagent_types.delete": "Удалить",
        "tui.subagent_types.save": "Сохранить",
        "tui.subagent_types.cancel": "Отмена",
        "tui.subagent_types.refresh": "Обновить",
        "tui.subagent_types.close": "Закрыть",
        "tui.subagent_types.list_hint": "Встроенные типы только для чтения · Свои типы: промпт, skills, MCP, модель, CLI",
        "tui.subagent_types.form_title": "Свой тип субагента",
        "tui.subagent_types.form_hint": "Имя (slug) · системный промпт · tools · skills · MCP · модель · внешний CLI",
        "tui.subagent_types.tools": "Инструменты",
        "tui.subagent_types.skills": "Skills (allowlist для типа)",
        "tui.subagent_types.mcp": "MCP-серверы",
        "tui.subagent_types.model": "Слот модели",
        "tui.subagent_types.external_cli": "Внешний CLI (holix launch)",
        "tui.subagent_types.builtin": "встроенный",
        "tui.subagent_types.custom": "свой",
        "tui.subagent_types.empty": "Типы субагентов не найдены.",
        "tui.subagent_types.select_type": "Выберите тип · встроенные нельзя редактировать здесь",
        "tui.subagent_types.builtin_readonly": "Встроенные типы заданы в коде и не редактируются в TUI.",
        "tui.subagent_types.not_found": "Свой тип не найден.",
        "tui.subagent_types.prompt_required": "Нужен системный промпт.",
        "tui.subagent_types.saved": "Сохранён тип субагента: {name}",
        "tui.subagent_types.deleted": "Удалён тип субагента: {name}",
        "tui.subagent_types.error": "Менеджер типов субагентов: {error}",
        "tui.subagent_types.cli_hint": "В TUI: /subagent-types — создание своих типов субагентов.",
        "tui.subagent_types.list_footer": "Управление типами: /subagent-types",
        "tui.subagent_types.usage": "Использование: /subagent-types · /subagent-types list",
        "init.ack": "▸ /init — анализ проекта → {path} (режим: {mode})",
        "init.ack_scoped": "▸ /init — анализ проекта → {path} в `{dir}/` (режим: {mode})",
        "init.scope_dir": (
            "**Область проекта:** анализируй только каталог `{dir}/` (относительно корня workspace). "
            "Считай его корнем проекта для этой инициализации. "
            "Не сканируй соседние каталоги, если они не нужны для контекста."
        ),
        "init.busy": ("Агент занят предыдущим запросом. Дождитесь ответа или отправьте /stop."),
        "init.not_ready": "Агент не готов. Сначала настройте модель (holix models add).",
        "init.large_hint": (
            "Это **большой репозиторий**. Строго соблюдай лимит чтения — "
            "полноту дают точечные `/init <подкаталог>` по субпроектам, "
            "а не один исчерпывающий проход."
        ),
        "init.scan.header": "## Предсканирование (автоматически)",
        "init.scan.scope": "Область: `{dir}` — ~{files} файлов (без vendor/cache-каталогов).",
        "init.scan.large_flag": (
            "**Большой репозиторий** — следуй правилам бюджета ниже; не пересканируй всё дерево."
        ),
        "init.scan.top_dirs": "Каталоги верхнего уровня: {dirs}",
        "init.scan.subprojects": "Обнаруженные субпроекты (цели для `/init <путь>`):\n{items}",
        "init.scan.manifests": "Манифесты пакетов / сборки:",
        "init.scan.readmes": "README / contributing:",
        "init.scan.doc_dirs": "Каталоги документации: {dirs}",
        "init.scan.extensions": "Типы файлов (выборка): {summary}",
        "init.scan.tree": "Дерево каталогов (усечено):",
        "init.scan.subprojects_heading": "Субпроекты",
        "init.scan.skeleton_note": "Авточерновик от предсканирования /init — дополни разделы ниже",
        "init.scan.prefill_heading": "Предзаполнено из скана",
        "init.scan.prefill_files": "Примерно {count} исходных файлов в области",
        "init.scan.prefill_scope": "Каталог области: `{dir}`",
        "init.scan.tree_heading": "Дерево каталогов",
        "init.holix_template": """# Контекст проекта (Holix)

> Создано командой `/init`. Обновляйте при существенных изменениях кодовой базы.

## Обзор
- Назначение:
- Основные пользователи / потребители:
- Тип репозитория (монорепо, сервис, библиотека, …):

## Структура каталогов
```
(дерево — с пояснениями важных папок)
```

## Технологический стек
- Языки:
- Фреймворки:
- БД / очереди / кэши:
- Менеджеры пакетов и сборка:

## Архитектура
- Схема верхнего уровня (текст или mermaid):
- Основные слои / bounded contexts:
- Точки входа (CLI, HTTP, воркеры, …):

## REST / HTTP API (если есть)
- Базовый URL / версионирование:
- Аутентификация:
- Карта маршрутов (метод, путь, handler/модуль, назначение):
- Паттерны запросов/ответов:

## Ключевые модули и зоны ответственности
| Модуль / пакет | Роль |
|----------------|------|

## Конфигурация и окружение
- Файлы конфигурации:
- Обязательные переменные окружения:
- Работа с секретами:

## Индекс документации
| Путь | Что описывает |
|------|---------------|

## Рабочий процесс разработки
- Установка:
- Локальный запуск:
- Тесты:
- Линт / форматирование:

## Соглашения по коду
- Стиль / правила линтера:
- Именование:
- Обработка ошибок / логирование:
- Подход к тестированию:

## Важные файлы
| Файл | Почему важен |

## Заметки и подводные камни
- …""",
        "init.user_message": """Выполни **инициализацию проекта** для текущей рабочей директории.

## Цель
Подготовь точный справочник проекта в **`{path}`**. **Черновик уже существует** по этому пути с данными предсканирования — **дополни и отредактируй его**, не начинай с нуля.
Все будущие агенты в этом репозитории будут опираться на этот файл в первую очередь.

## Отчёт предсканирования (не повторяй это обнаружение)
{scan_report}

## Как работать
1. **Сначала прочитай существующий `{path}`** — там уже есть дерево каталогов, список манифестов и разделы шаблона.
2. **Бюджет:** не более **~20 вызовов `read_file`** суммарно. Приоритет: корневой README, манифесты из отчёта, по одному репрезентативному файлу на крупный пакет, спецификации API при наличии.
3. **Не** запускай широкий рекурсивный `list_directory` и обход всего репо через `find`/`tree` — структура уже снята предсканированием.
4. `run_terminal_command` — только для быстрых ограниченных проверок (`head`, `rg -l` с лимитами), если манифест указывает на скрипты.
5. Для **монорепо** (несколько субпроектов в отчёте): опиши обзор репозитория; по каждому субпроекту — 2–3 предложения; укажи, что углубление даёт `/init <путь>`. **Не** читай все субпроекты за один проход.
6. Заполняй разделы шаблона **конкретными фактами** из прочитанных файлов; неизвестное помечай «уточнить», а не выдумывай.
7. Обновляй **`{path}` через `update_holix_section`** — **один раздел за вызов** (заголовок + текст до ~30 строк). Это основной tool для /init.
8. **`patch_file`** — только для мелких правок (1–3 замены, каждая `new_string` до 15 строк). **Никогда** не вызывай `write_file` для HOLIX.md.
9. **Не** пиши текст вроде «создаю справочник» — сразу вызывай `update_holix_section`, затем следующий раздел.

## Результат
- Заверши **`{path}`** несколькими вызовами **`update_holix_section`** (сохрани предзаполненное дерево и таблицу субпроектов).
- **Запрещено:** `write_file` на `{path}`, большие `patch_file`, или полный справочник в тексте ответа.
- Используй структуру ниже (заполни каждый раздел; добавляй подразделы по необходимости).
- Будь **конкретным** (пути к файлам, имена модулей, примеры команд из реальных конфигов).
- **Не пропускай** API и слой данных, если они есть в проекте.
- **Весь текст в `{path}` пиши на русском** (заголовки, описания, таблицы).

## Обязательный шаблон
```markdown
{template}
```

По завершении укажи абсолютный путь к записанному файлу и дай краткое резюме на 5–10 строк о том, что задокументировал.""",
        "prompt.lang_block": (
            "## Язык\n"
            "Пользователь выбрал язык интерфейса русский (`/lang ru`).\n"
            "**Весь видимый пользователю текст пиши ТОЛЬКО на русском** — финальные ответы, "
            "промежуточные планы, списки шагов, анализ, итоги, уточняющие вопросы и "
            "комментарии до/после вызова tools — даже если пользователь пишет на другом языке.\n"
            "Никогда не отдавай внутренние рассуждения (chain-of-thought) как единственный ответ — "
            "всегда формулируй нормальный ответ пользователю на русском.\n"
            "На вопросы о статусе («что делаешь», «какой статус», «какие задачи»): при необходимости "
            "вызови `list_subagents()`, затем ответь по-русски — что делаешь сейчас и какие задачи "
            "в работе.\n"
            "Исключение: другой язык только если пользователь явно попросит ответить на нём "
            "в конкретном сообщении."
        ),
        "llm.truncated": (
            "Ответ обрезан лимитом токенов модели. "
            "Остановилась, не повторяя фразу — попросите продолжить, "
            "сузьте задачу или выберите модель с большим бюджетом ответа."
        ),
        "llm.content_filter": "Модель отклонила запрос (content filter).",
        "llm.reasoning_only": (
            "Модель завершила размышление без видимого ответа. Попробуйте ещё раз."
        ),
        "work_status.title": "**Статус работы**",
        "work_status.main_label": "**Главный агент:** {state}",
        "work_status.main_idle": "свободен — жду ваш запрос",
        "work_status.main_busy": "обрабатываю запрос",
        "work_status.tasks_label": "**Текущие задачи:**",
        "work_status.tasks_unknown": "- (в этой сессии задача ещё не зафиксирована)",
        "work_status.last_action_label": "**Последнее действие:**",
        "work_status.action_unknown": "(не было недавнего ответа ассистента)",
        "work_status.subagents_disabled": "**Субагенты:** отключены в профиле",
        "work_status.subagents_empty": (
            "**Субагенты:** сейчас нет запущенных.\nЗапуск: `/subagent-spawn coder <задача>`"
        ),
        "work_status.subagents_header": "**Субагенты:** всего {total} (в работе: {running})",
        "work_status.subagent_line": "• `{name}` — {status}{preview}",
        "live.thinking": "Думаю…",
        "live.working": "Работаю…",
        "live.reasoning": "Модель размышляет…",
        "live.thinking_step": "Шаг {step}: размышление…",
        "live.holix_thinking": "Holix думает… (режим: {mode})",
        "live.processing": "Holix обрабатывает запрос…",
        "live.still_working": "Holix всё ещё работает…",
        "live.generating_plan": "Формирую план выполнения (таймаут: {timeout} с)…",
        "live.plan_review": "⏸ Проверка плана ({count} шагов)",
        "live.answer_sent": "Ответ отправлен отдельным сообщением ↓",
        "live.bg_process_started": "🟢 Фоновый процесс запущен\n<code>{label}</code>",
        "live.bg_process_stopped": "⏹ Фоновый процесс остановлен\n<code>{label}</code>",
        "live.bg_process_error": "⚠ Ошибка фонового процесса\n<code>{label}</code>\n{summary}",
        "live.plan.phase_start": "📋 Режим планирования: готовлю построение плана…",
        "live.plan.phase_context": "📋 Собираю контекст памяти и инструментов (память: {memories}, инструменты: {tools})…",
        "live.plan.phase_handbook": "📋 Загружаю handbook / specs проекта (workspace: {path})…",
        "live.plan.phase_handbook_init": "📋 Handbook нет — запускаю pre-scan /init…",
        "live.plan.phase_llm": "📋 Модель строит план (model: {model}, таймаут: {timeout} с)…",
        "live.plan.phase_llm_wait": "📋 Модель всё ещё генерирует план… прошло {elapsed} с (таймаут {timeout} с)",
        "live.plan.phase_attempt": "📋 Попытка генерации плана {attempt}/{total}…",
        "live.plan.phase_received": "📋 Черновик плана получен ({chars} символов) — разбираю…",
        "live.plan.phase_quality": "📋 Проверяю качество плана (шаги, отчёт)…",
        "live.plan.phase_retry": "📋 План недостаточно детальный — уточняю у модели ({reason})…",
        "live.plan.phase_save": "📋 Сохраняю черновик плана ({steps} шагов) для проверки…",
        "live.plan.phase_ready": "📋 План готов: {steps} шагов — жду вашего подтверждения",
        "live.plan.phase_waiting_review": "⏸ Жду, пока вы одобрите или уточните план ({steps} шагов)…",
        "plan.title": "📋 План выполнения — {count} шагов",
        "plan.task_label": "Задача:",
        "plan.analysis": "📊 Анализ",
        "plan.summary": "Кратко:",
        "plan.complexity": "Сложность:",
        "plan.questions": "❓ Уточняющие вопросы",
        "plan.questions_hint": "Опишите, что изменить, чтобы ответить на эти вопросы.",
        "plan.constraints": "🔒 Ограничения",
        "plan.architecture": "🏗️ Архитектура",
        "plan.approach": "Подход:",
        "plan.tech_stack": "Стек:",
        "plan.structure": "Структура:",
        "plan.risks": "⚡ Риски и меры",
        "plan.risk_col": "Риск",
        "plan.mitigation_col": "Мера",
        "plan.steps": "📝 Шаги выполнения",
        "plan.step": "Шаг {num}",
        "plan.step_in_progress": "в работе",
        "plan.step_failed": "ошибка",
        "plan.tools": "Инструменты:",
        "plan.subagent": "Субагент:",
        "plan.parallel": "Параллельная группа:",
        "plan.depends": "Зависит от:",
        "plan.expected": "Ожидаемый результат:",
        "plan.success": "Критерий успеха:",
        "plan.reasoning": "💭 Обоснование",
        "plan.no_description": "Без описания",
        "plan.refine_hint": "_Или напишите текстом, что изменить в плане._",
        "plan.approval_hint": "_Ответьте **да** для запуска разработки, **нет** для отмены или опишите правки для доработки плана._",
        "plan.clarify.title": "❓ Нужны уточнения перед планированием",
        "plan.clarify.reason": "Почему нужны уточнения:",
        "plan.clarify.questions": "Вопросы",
        "plan.clarify.hint": "_Ответьте на вопросы выше. Напишите **продолжай с допущениями**, чтобы пропустить, или **нет** для отмены._",
        "plan.clarify.default_question": "Уточните требования к задаче.",
        "plan.clarify.rejected": "Планирование отменено. Напишите снова, когда будете готовы уточнить детали.",
        "plan.report.default_title": "План разработки",
        "plan.report.section_summary": "1. Общее резюме",
        "plan.report.goal": "Цель:",
        "plan.report.key_decisions": "Ключевые решения:",
        "plan.report.critical_risks": "Критические риски:",
        "plan.report.section_stages": "2. Этапы разработки",
        "plan.report.stage": "Этап {num}",
        "plan.report.duration": "Ориентировочная длительность:",
        "plan.report.section_priorities": "3. Приоритеты",
        "plan.report.priority_mvp": "Критично для MVP (блокирует запуск)",
        "plan.report.priority_later": "Важно, но можно отложить на 1–2 итерации",
        "plan.report.priority_optional": "Опционально / на будущее",
        "plan.report.section_dependencies": "4. Зависимости между задачами",
        "plan.report.dep_task": "Задача",
        "plan.report.dep_depends": "Зависит от",
        "plan.report.dep_unblocks": "Что разблокирует",
        "plan.report.parallel_work": "Параллельная работа возможна:",
        "plan.report.section_blockers": "5. Блокеры и риски",
        "plan.report.blocker_risk": "Риск",
        "plan.report.blocker_probability": "Вероятность",
        "plan.report.blocker_impact": "Влияние",
        "plan.report.blocker_mitigation": "Mitigation",
        "plan.report.section_manual": "6. Ручные действия",
        "plan.report.manual_action": "Действие",
        "plan.report.manual_when": "Когда",
        "plan.report.manual_who": "Кто",
        "plan.report.section_estimates": "7. Оценка стоимости/времени",
        "plan.report.estimate_stage": "Этап",
        "plan.report.estimate_hours": "Часы",
        "plan.report.estimate_sp": "Story Points",
        "plan.report.total": "ИТОГО:",
        "plan.report.hours_unit": "часов",
        "plan.report.calendar": "В календарном времени:",
        "plan.report.buffer": "Буфер на непредвиденное:",
        "plan.report.section_stack": "8. Рекомендуемый стек и архитектура",
        "plan.report.stack_tech": "Стек технологий",
        "plan.report.stack_patterns": "Архитектурные паттерны",
        "plan.report.stack_fixes": "Критические архитектурные исправления (по сравнению с ТЗ)",
        "studio.wait_for_run": "Дождитесь ответа или нажмите Stop.",
        "studio.timeout": "Превышено время выполнения. Попробуйте ещё раз или /models.",
        "supervisor.repeating": "Повтор: {target}",
        "supervisor.last_result": "Последний результат: {result}",
        "supervisor.stuck": "Что застряло: {problem}",
        "supervisor.tool": "Инструмент: {tool}",
        "supervisor.known": "Уже известно: {known}",
        "supervisor.last_tool_result": "Последний результат инструмента: {result}",
        "supervisor.asked_agent": "Что супервизор уже просил агента сделать: {next}",
        "supervisor.fallback_q": (
            "Субагент `{name}` зациклился на одном инструменте ({summary}). "
            "Что ему делать дальше — или остановить?"
        ),
        "supervisor.q.inspect": (
            "Кодер застрял на инспекции библиотек вместо того, чтобы писать файлы{target}. "
            "Реализовать на известных API FastAPI/Dishka, пропустить шаг "
            "или нужен другой подход?"
        ),
        "supervisor.q.noop_write": (
            "Кодер снова перезаписывает файлы, которые уже совпадают с диском{target}. "
            "Остановить и финализировать, один раз прогнать тесты или править конкретный файл?"
        ),
        "supervisor.q.launch": (
            "Кодер снова поднимает сервер в terminal вместо "
            "start_background_process{target}. "
            "Переключить на фоновый инструмент, пропустить сервер или остановить?"
        ),
        "supervisor.q.venv": (
            "Кодер крутит `ls/grep` внутри .venv{target}. "
            "Этих пакетов нет. Реализовать без них, сделать `uv add` конкретного пакета "
            "или остановиться и ждать вас?"
        ),
        "supervisor.q.install": (
            "Кодер повторяет одну и ту же команду установки{target}. "
            "Продолжить с текущими зависимостями, поставить названный пакет или остановить?"
        ),
        "supervisor.q.terminal": (
            "Кодер повторяет одну и ту же команду terminal{target}. "
            "Что сделать вместо этого (какой файл править, какую команду, или остановить)?"
        ),
        "supervisor.q.read": (
            "Кодер снова читает один и тот же файл{target}. "
            "Какое изменение сделать — или остановить?"
        ),
        "supervisor.q.search": (
            "Кодер застрял на повторном grep/glob{target}. "
            "Какой путь открыть — или прекратить поиск?"
        ),
        "supervisor.q.write": (
            "Кодер снова перезаписывает один и тот же файл{target}. "
            "Финализировать, править другой файл или остановить?"
        ),
        "supervisor.q.web": (
            "Кодер крутит web_search/web_fetch{target}. "
            "Писать по уже найденному, открыть конкретный URL или остановить?"
        ),
        "supervisor.q.generic": (
            "Кодер зациклился на `{tool}`{target}. Что делать дальше — или остановить?"
        ),
        "supervisor.p.inspect": "инспекция библиотек через terminal",
        "supervisor.p.noop_write": "перезапись файлов, которые уже совпадают с диском",
        "supervisor.p.launch": "запуск долгоживущего сервера в обычном terminal",
        "supervisor.p.venv": "поиск пакетов внутри виртуального окружения",
        "supervisor.p.install": "повтор одной и той же команды установки",
        "supervisor.p.terminal": "повтор одной и той же команды `{tool}`",
        "supervisor.p.read": "повторное чтение одного и того же файла",
        "supervisor.p.search": "повтор одного и того же поиска",
        "supervisor.p.write": "повторная перезапись одного и того же файла",
        "supervisor.p.web": "повтор одного и того же web_search/web_fetch",
        "supervisor.p.generic": "повтор `{tool}`",
        "supervisor.k.inspect": "inspect/python -c по сторонним пакетам не пишет проект.",
        "supervisor.k.noop_write": "write_file уже ответил, что содержимое не изменилось.",
        "supervisor.k.launch": "uvicorn/npm в foreground блокирует агента и не попадает в процессы Studio.",
        "supervisor.k.venv_absent": "Список .venv уже показал, что этих пакетов нет. Повторный ls/grep их не установит.",
        "supervisor.k.venv": "Поиск в site-packages не выполняет задачу.",
        "supervisor.k.install": "команда установки уже выполнялась; повтор — не прогресс.",
        "supervisor.k.terminal_result": "Последняя команда уже вернула ответ (включая пустой / not found).",
        "supervisor.k.terminal": "Повтор той же shell-команды результат не изменит.",
        "supervisor.k.read": "содержимое этого файла уже есть.",
        "supervisor.k.search": "поиск уже вернул совпадения (или их нет).",
        "supervisor.k.write": "ещё одна перезапись того же пути — не новая работа.",
        "supervisor.k.web": "результат этой страницы/запроса уже есть.",
        "supervisor.k.generic": "тот же вызов инструмента новой информации не даст.",
        "skill.notice.pending": "Предложен новый skill: {name}",
        "skill.notice.auto": "Новый skill принят автоматически: {name}",
        "skill.notice.score": "Качество {score}/100 · {tier} — {hint}",
        "skill.notice.actions": "Примите или отклоните кнопками ниже, либо откройте Настройки → Skills.",
        "skill.btn.approve": "Принять",
        "skill.btn.reject": "Отклонить",
        "skill.cb.approved": "Skill принят",
        "skill.cb.rejected": "Skill отклонён",
        "skill.cb.missing": "Черновик не найден (уже решили?)",
        "skill.cb.error": "Не удалось применить: {error}",
    },
}


def t(key: str, locale: str | None = None, **kwargs: object) -> str:
    loc = normalize_locale(locale)
    catalog = MESSAGES.get(loc) or MESSAGES[DEFAULT_LOCALE]
    template = catalog.get(key) or MESSAGES[DEFAULT_LOCALE].get(key) or key
    if kwargs:
        return template.format(**kwargs)
    return template
