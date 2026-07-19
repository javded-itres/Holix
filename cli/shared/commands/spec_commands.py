"""Shared /spec (SDD) slash commands for TUI, Studio, Telegram."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.sdd.projects import discover_sdd_projects, resolve_project_root
from core.sdd.store import SpecStore


def _workspace(host: Any) -> Path:
    root = getattr(host, "workspace_root", None)
    if root:
        return Path(root).expanduser().resolve()
    session = getattr(host, "_session", None)
    if session is not None and getattr(session, "workspace_root", None):
        return Path(session.workspace_root).expanduser().resolve()
    return Path.cwd().resolve()


def _store(host: Any, project: str | None = None) -> SpecStore:
    return SpecStore(resolve_project_root(_workspace(host), project))


def _write(host: Any, text: str) -> None:
    if hasattr(host, "emit_system"):
        import asyncio

        result = host.emit_system(text)
        if asyncio.iscoroutine(result):
            # schedule if loop running; else transcript
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(result)
                return
            except RuntimeError:
                pass
    host.transcript_write(text)


def _parse_spec_args(rest: str) -> tuple[list[str], str]:
    """Return (positional tokens, project path). Supports project= / --project / -p."""
    bits = [b for b in (rest or "").split() if b]
    project = ""
    out: list[str] = []
    i = 0
    while i < len(bits):
        b = bits[i]
        if b.startswith("project="):
            project = b.split("=", 1)[1].strip()
            i += 1
            continue
        if b in ("--project", "-p") and i + 1 < len(bits):
            project = bits[i + 1]
            i += 2
            continue
        out.append(b)
        i += 1
    return out, project


async def run_spec_command(host: Any, command: str) -> None:
    """Handle /spec family.

    Multi-project: pass project path as last arg or ``project=apps/web`` /
    ``--project apps/web``. Empty project = workspace root openspec.
    """
    parts = (command or "").strip().split(maxsplit=2)
    # parts[0] == /spec
    sub = parts[1].lower() if len(parts) > 1 else ""
    rest = parts[2] if len(parts) > 2 else ""
    tokens, project = _parse_spec_args(rest)
    primary = tokens[0] if tokens else ""
    secondary = tokens[1] if len(tokens) > 1 else ""

    # Positional project when flags not used:
    #   /spec apply <id> <project>
    #   /spec mode <id> <mode> <project>
    #   /spec init <project>
    if not project:
        if sub == "mode" and len(tokens) >= 3:
            project = tokens[2]
        elif sub in ("apply", "archive", "status", "propose", "new", "create") and len(
            tokens
        ) >= 2:
            project = tokens[1]
        elif sub == "init" and tokens:
            project = tokens[0]
            primary = ""
            secondary = ""

    store = _store(host, project or None)
    proj_label = project or "."

    if sub in ("", "status", "list") and not primary:
        projects = discover_sdd_projects(_workspace(host))
        if not projects and not store.is_initialized():
            _write(
                host,
                "SDD not initialized. Run `/spec init` or `/spec init <project-path>` "
                "or ask the agent to call sdd_init.",
            )
            return
        lines = ["**SDD status**"]
        if projects:
            lines.append(f"projects: {len(projects)}")
            for p in projects[:30]:
                lines.append(f"  • `{p['path'] or '.'}` → {p.get('openspec')}")
        overview = store.status_overview()
        lines.append(f"active project: `{proj_label}`")
        lines.append(f"path: `{overview.get('path')}`")
        specs = overview.get("specs") or []
        lines.append(f"specs: {len(specs)}")
        for s in specs[:20]:
            lines.append(f"  • {s['domain']} ({s.get('requirements', 0)} reqs)")
        changes = overview.get("changes") or []
        lines.append(f"open changes: {len(changes)}")
        for c in changes[:20]:
            mode = c.get("apply_mode") or "—"
            ready = "ready" if c.get("apply_ready") else "draft"
            lines.append(
                f"  • `{c['change_id']}` {ready} · "
                f"{c.get('tasks_done', 0)}/{c.get('tasks_total', 0)} tasks · mode={mode}"
            )
        lines.append("")
        lines.append(
            "`/spec init [project]` · `/spec propose <id> [project]` · "
            "`/spec apply <id> [project]` · `/spec archive <id> [project]` · "
            "`/spec status [id] [project]`"
        )
        _write(host, "\n".join(lines))
        return

    if sub == "init":
        try:
            result = store.init()
            _write(host, f"SDD init ({proj_label}): {result}")
        except Exception as exc:
            _write(host, f"Error: {exc}")
        return

    if sub in ("propose", "new", "create"):
        change_id = primary
        if not change_id:
            _write(
                host,
                "Usage: `/spec propose <change-id> [project]` "
                "e.g. `/spec propose oauth-login apps/web`",
            )
            return
        if not store.is_initialized():
            store.init()
        domain = "example"
        specs = store.list_specs()
        if specs:
            domain = specs[0]["domain"]
        try:
            created = store.create_change(change_id, domain=domain)
            apply_hint = (
                f"`/spec apply {change_id} {project}`"
                if project
                else f"`/spec apply {change_id}`"
            )
            _write(
                host,
                f"Created change `{created['change_id']}` at `{created['path']}` "
                f"(project `{proj_label}`).\n"
                f"Fill proposal/specs/tasks (with assignees), then {apply_hint}.",
            )
        except FileExistsError:
            _write(host, f"Change already exists: {change_id}")
        except Exception as exc:
            _write(host, f"Error: {exc}")
        return

    if sub == "status" and primary:
        change_id = primary
        try:
            st = store.change_status(change_id)
            _write(host, f"```json\n{st.to_dict()}\n```")
        except Exception as exc:
            _write(host, f"Error: {exc}")
        return

    if sub == "mode":
        # /spec mode <id> <self|subagents|hybrid> [project]
        change_id = primary
        mode = secondary
        if not change_id or not mode:
            _write(
                host,
                "Usage: `/spec mode <change-id> self|subagents|hybrid [project]`",
            )
            return
        try:
            result = store.set_apply_mode(change_id, mode)
            _write(host, f"Apply mode set ({proj_label}): {result}")
        except Exception as exc:
            _write(host, f"Error: {exc}")
        return

    if sub == "apply":
        change_id = primary
        if not change_id:
            _write(host, "Usage: `/spec apply <change-id> [project]`")
            return
        try:
            st = store.change_status(change_id)
            if not st.apply_mode:
                req = store.request_apply_mode(change_id)
                _write(host, req.get("prompt") or "Choose apply mode first.")
                mode_cmd = (
                    f"`/spec mode {change_id} self|subagents|hybrid {project}`"
                    if project
                    else f"`/spec mode {change_id} self|subagents|hybrid`"
                )
                apply_cmd = (
                    f"`/spec apply {change_id} {project}`"
                    if project
                    else f"`/spec apply {change_id}`"
                )
                _write(host, f"Then: {mode_cmd} and re-run {apply_cmd}.")
                return
            plan = store.begin_apply(change_id)
            if not plan.get("ok"):
                missing = plan.get("missing") or []
                err = plan.get("error") or "not ready"
                extra = f" Missing: {', '.join(missing)}." if missing else ""
                _write(host, f"Cannot apply: {err}.{extra}")
                return
            # Ask agent to implement via synthetic message if possible
            lines = [
                f"Apply plan for `{change_id}` "
                f"(project=`{proj_label}`, mode={plan['apply_mode']}):",
            ]
            for item in plan.get("plan") or []:
                lines.append(
                    f"- [{item.get('id')}] {item.get('text')} → executor=`{item.get('executor')}`"
                )
            lines.append("")
            lines.append(
                "Implement remaining tasks. Use **exact executor** names above "
                "(custom types like coder-python — never replace with built-in coder). "
                "Call `sdd_apply` (auto-dispatches) or `sdd_dispatch`. "
                "Mark done with `sdd_check_task`."
            )
            _write(host, "\n".join(lines))
            # Auto-dispatch when session agent is ready (subagents/hybrid)
            agent = getattr(host, "agent", None) or getattr(
                getattr(host, "_session", None), "agent", None
            )
            mode = (plan.get("apply_mode") or "").strip().lower()
            if agent is not None and mode in ("subagents", "hybrid"):
                try:
                    from core.sdd.dispatch import dispatch_change_tasks

                    disp = await dispatch_change_tasks(
                        store, change_id, parent_agent=agent
                    )
                    spawned = disp.get("spawned") or []
                    if spawned:
                        _write(
                            host,
                            "Auto-dispatched by tasks.md assignee:\n"
                            + "\n".join(
                                f"- task {j.get('task_id')} → job `{j.get('job_id')}` "
                                f"(type={j.get('executor')})"
                                for j in spawned
                            ),
                        )
                    if disp.get("errors"):
                        _write(host, "Dispatch errors: " + "; ".join(disp["errors"]))
                except Exception as exc:
                    _write(host, f"Auto-dispatch skipped: {exc}")
            proj_arg = f' project="{project}"' if project else ""
            msg = (
                f"Apply SDD change `{change_id}` now (project `{proj_label}`). "
                f"Mode is already set to `{plan['apply_mode']}`. "
                f"Use tools with{proj_arg or ' project=\"\" (workspace root)'}. "
                f"Call sdd_apply{proj_arg} (auto-dispatches subagents by tasks.md assignee — "
                f"e.g. coder-python, NOT built-in coder). "
                "Wait for jobs with wait_subagent_result; do main tasks yourself; "
                "sdd_check_task as you go."
            )
            if hasattr(host, "_start_agent_run_guarded"):
                await host._start_agent_run_guarded(msg)
            elif hasattr(host, "_send_message"):
                await host._send_message(msg)
        except FileNotFoundError as exc:
            _write(
                host,
                f"Change not found in project `{proj_label}`: {exc}. "
                "Pass the project path: `/spec apply <id> <project-path>`.",
            )
        except Exception as exc:
            _write(host, f"Error: {exc}")
        return

    if sub == "archive":
        change_id = primary
        if not change_id:
            _write(host, "Usage: `/spec archive <change-id> [project]`")
            return
        try:
            result = store.archive(change_id)
            _write(host, f"Archived ({proj_label}): {result}")
        except Exception as exc:
            _write(host, f"Error: {exc}")
        return

    _write(
        host,
        "SDD: `/spec` · `/spec init [project]` · `/spec propose <id> [project]` · "
        "`/spec status [id] [project]` · `/spec mode <id> self|subagents|hybrid [project]` · "
        "`/spec apply <id> [project]` · `/spec archive <id> [project]`",
    )
