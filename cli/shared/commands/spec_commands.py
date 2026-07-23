"""Shared /spec (SDD) slash commands for TUI, Studio, Telegram, and MAX."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from core.sdd.projects import discover_sdd_projects, resolve_project_root
from core.sdd.store import SpecStore


def _workspace(host: Any) -> Path:
    """Resolve the agent workspace root for SDD paths.

    Telegram/MAX hosts do not always expose ``workspace_root``; fall back to
    agent config and the profile workspace directory.
    """
    root = getattr(host, "workspace_root", None)
    if root:
        return Path(root).expanduser().resolve()

    session = getattr(host, "_session", None)
    if session is not None:
        sroot = getattr(session, "workspace_root", None)
        if sroot:
            return Path(sroot).expanduser().resolve()

    agent = getattr(host, "agent", None)
    if agent is not None:
        cfg = getattr(agent, "config", None)
        if cfg is not None:
            aroot = getattr(cfg, "workspace_root", None)
            if aroot:
                return Path(aroot).expanduser().resolve()

    profile = (
        getattr(host, "profile", None)
        or (getattr(session, "profile", None) if session is not None else None)
        or "default"
    )
    try:
        from core.profile_keys import profile_dir

        ws = profile_dir(str(profile)) / "workspace"
        if ws.is_dir():
            return ws.resolve()
    except Exception:
        pass

    return Path.cwd().resolve()


def _store(host: Any, project: str | None = None) -> SpecStore:
    return SpecStore(resolve_project_root(_workspace(host), project))


async def _write(host: Any, text: str) -> None:
    """Deliver slash feedback on TUI, Studio, Telegram, and MAX."""
    body = (text or "").strip()
    if not body:
        return

    emit = getattr(host, "emit_system", None)
    if emit is not None:
        result = emit(body)
        if asyncio.iscoroutine(result):
            await result
        return

    send_plain = getattr(host, "_send_plain", None)
    if send_plain is not None:
        result = send_plain(body)
        if asyncio.iscoroutine(result):
            await result
        return

    send_text = getattr(host, "_send_text", None)
    if send_text is not None:
        result = send_text(body)
        if asyncio.iscoroutine(result):
            await result
        return

    send_html = getattr(host, "_send_html", None)
    if send_html is not None:
        # Best-effort plain delivery when host only exposes HTML sender.
        result = send_html(body)
        if asyncio.iscoroutine(result):
            await result
        return

    host.transcript_write(body)


async def _dispatch_agent(host: Any, message: str) -> None:
    from cli.shared.commands.project_init import dispatch_agent_message

    await dispatch_agent_message(host, message)


def _split_tokens(text: str) -> list[str]:
    """Split command args, honouring single/double quotes (Telegram-friendly)."""
    import shlex

    raw = (text or "").strip()
    if not raw:
        return []
    try:
        return shlex.split(raw, posix=True)
    except ValueError:
        # Unbalanced quotes — fall back to whitespace split.
        return [b for b in raw.split() if b]


def _looks_like_project_path(token: str) -> bool:
    """True when *token* is a project path, not free-text request prose."""
    s = (token or "").strip()
    if not s or any(ch.isspace() for ch in s):
        return False
    # Paths / relative project roots
    if "/" in s or s in {".", ".."}:
        return True
    # Single path segment: short slug without sentence punctuation
    if len(s) > 64:
        return False
    # Cyrillic / long natural language → request, not project
    if any(ord(ch) > 127 for ch in s):
        return False
    if any(ch in s for ch in ",:;!?"):
        return False
    # ASCII path segment (apps, backend, my-app)
    return all(ch.isalnum() or ch in "._-" for ch in s)


def _parse_spec_args(rest: str) -> tuple[list[str], str, str]:
    """Return (positional tokens, project path, free-text request after ``--``)."""
    raw = (rest or "").strip()
    request = ""
    if " -- " in f" {raw} ":
        # Support: /spec propose id -- long request text
        head, _, tail = raw.partition(" -- ")
        raw = head.strip()
        request = tail.strip()

    bits = _split_tokens(raw)
    project = ""
    out: list[str] = []
    i = 0
    while i < len(bits):
        b = bits[i]
        if b.startswith("project="):
            project = b.split("=", 1)[1].strip().strip("\"'")
            i += 1
            continue
        if b in ("--project", "-p") and i + 1 < len(bits):
            project = bits[i + 1].strip().strip("\"'")
            i += 2
            continue
        out.append(b)
        i += 1
    return out, project, request


def _resolve_create_fill_args(
    tokens: list[str],
    project: str,
    request: str,
) -> tuple[str, str, str]:
    """Split create/propose/fill args into (change_id, project, request).

    Accepts Telegram-friendly forms::

        /spec create company "long description…"
        /spec create company long description without quotes
        /spec create company apps/web -- long description
        /spec create company project=apps/web -- long description
    """
    change_id = tokens[0] if tokens else ""
    rest = list(tokens[1:]) if len(tokens) > 1 else []
    proj = (project or "").strip()
    req = (request or "").strip()

    if not rest:
        return change_id, proj, req

    if req:
        # Explicit ``-- request`` already set; leftover token may be project.
        if not proj and len(rest) == 1 and _looks_like_project_path(rest[0]):
            proj = rest[0]
        elif not proj and rest and _looks_like_project_path(rest[0]):
            proj = rest[0]
        return change_id, proj, req

    if not proj and rest and _looks_like_project_path(rest[0]):
        proj = rest[0]
        rest = rest[1:]

    if rest:
        req = " ".join(rest).strip()
    return change_id, proj, req


def _usage() -> str:
    return (
        "SDD `/spec`:\n"
        "• `/spec` · `/spec list` — projects & open changes\n"
        "• `/spec init [project]` — create openspec/\n"
        "• `/spec create|propose <id> [project] [\"request\" | -- request]`\n"
        "• `/spec show|view <id> [project]` — status + proposal/tasks preview\n"
        "• `/spec fill <id> [project] [\"request\" | -- request]`\n"
        "• `/spec mode <id> self|subagents|hybrid [project]`\n"
        "• `/spec apply|run <id> [project]` — start implementation\n"
        "• `/spec archive <id> [project]` — merge & archive"
    )


def _understanding_prompt(
    *,
    change_id: str,
    project: str,
    request: str,
    threshold: int = 80,
    locale: str = "en",
) -> str:
    """Agent prompt when understanding gate is ON after create."""
    proj = project or ""
    proj_label = project or "."
    req = request.strip() or f"Change `{change_id}` (no free-text request — use stubs)."
    thr = max(1, min(100, int(threshold)))
    return (
        f"SDD change `{change_id}` created in project `{proj_label}`.\n"
        f"User request:\n{req}\n\n"
        f"Understanding gate is ON (threshold {thr}%). Status is clarifying at 0% — "
        f"do NOT set score=100 to skip questions and do NOT call sdd_write_artifact yet.\n"
        f"Locale={locale}.\n"
        f"Order:\n"
        f"1) sdd_status + sdd_list_specs / sdd_read_spec + archived changes + HOLIX.md "
        f"(/init-equivalent if project context is weak)\n"
        f"2) sdd_update_understanding with honest score (0–100), summary of what you know, "
        f"and residual open_questions\n"
        f"3) Ask the user only residual questions in chat; after each answer call "
        f"sdd_update_understanding again with user_answer and updated score\n"
        f"4) When score ≥ {thr}% (status ready), ask the user to proceed, then "
        f"sdd_confirm_understanding\n"
        f"5) Only after confirmed: fill via sdd_write_artifact (proposal, design, specs, tasks)\n"
        f"Work only on change_id=\"{change_id}\" project=\"{proj}\"."
    )


def _fill_prompt(
    *,
    change_id: str,
    project: str,
    request: str,
    locale: str = "en",
) -> str:
    proj = project or ""
    proj_label = project or "."
    req = request.strip() or f"Complete SDD change `{change_id}` from existing stubs and project context."
    return (
        f"SDD change `{change_id}` in project `{proj_label}`.\n"
        f"User request:\n{req}\n\n"
        f"Understanding gate is already unlocked for this fill — do NOT ask clarifying "
        f"questions and do NOT stop at stubs.\n"
        f"Write artifacts only in locale={locale}.\n"
        f"First call `sdd_status` (project=\"{proj}\", change_id=\"{change_id}\") and use "
        f"`artifact_paths` from the result. There is NO file specs.md at the change root.\n"
        f"MUST call `sdd_write_artifact` (project=\"{proj}\") for ALL of:\n"
        f"1) proposal (Why / What Changes / Impact — no HTML comments, no placeholders)\n"
        f"2) design (concrete approach)\n"
        f"3) specs — artifact=\"specs\" (writes specs/<domain>/spec.md; pass domain if known)\n"
        f"4) tasks — real numbered checklist from the request (not 'First concrete "
        f"step'); set assignee main or a subagent type; add depends_on when needed.\n"
        f"Do NOT use read_file/write_file on openspec/changes/.../specs.md (that path "
        f"does not exist). Do not loop on missing-file errors — write via sdd_write_artifact.\n"
        f"Then call `sdd_status` and report only what tools returned. "
        f"Do NOT invent paths or task lists without tool results."
    )


def _sdd_prefs(host: Any) -> Any:
    try:
        from core.sdd.prefs import SddPrefsStore

        profile = (
            getattr(host, "profile", None)
            or getattr(getattr(host, "_session", None), "profile", None)
            or "default"
        )
        return SddPrefsStore(str(profile)).get()
    except Exception:
        from core.sdd.prefs import SddPrefs

        return SddPrefs()


def _unlock_understanding_for_fill(
    store: SpecStore, change_id: str, *, request: str = ""
) -> None:
    """Allow sdd_write_artifact after explicit /spec fill (not on create when gate ON)."""
    from core.sdd.understanding import accept_request_understanding

    accept_request_understanding(
        store.project_root, change_id, request=request, unlock=True
    )


def _apply_agent_message(*, change_id: str, project: str, apply_mode: str) -> str:
    proj_label = project or "."
    proj_arg = f' project="{project}"' if project else ""
    return (
        f"Apply SDD change `{change_id}` now (project `{proj_label}`). "
        f"Mode is already set to `{apply_mode}`. "
        f"Use tools with{proj_arg or ' project=\"\" (workspace root)'}. "
        f"Call sdd_apply{proj_arg} (auto-dispatches subagents by tasks.md assignee — "
        f"e.g. coder-python, NOT built-in coder). "
        "Wait for jobs with wait_subagent_result; do main tasks yourself; "
        "sdd_check_task as you go."
    )


def _preview_file(path: Path, *, limit: int = 40) -> str:
    if not path.is_file():
        return "(missing)"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return f"(read error: {exc})"
    if len(lines) > limit:
        return "\n".join(lines[:limit]) + f"\n… ({len(lines) - limit} more lines)"
    return "\n".join(lines) if lines else "(empty)"


async def run_spec_command(host: Any, command: str) -> None:
    """Handle /spec family for all interactive hosts.

    Multi-project: pass project path as last arg or ``project=apps/web`` /
    ``--project apps/web``. Empty project = workspace root openspec.
    Optional free text after `` -- `` is used as the user request for fill/create.
    """
    raw = (command or "").strip()
    parts = raw.split(maxsplit=2)
    # parts[0] == /spec
    sub = parts[1].lower() if len(parts) > 1 else ""
    rest = parts[2] if len(parts) > 2 else ""
    tokens, project, request = _parse_spec_args(rest)
    primary = tokens[0] if tokens else ""
    secondary = tokens[1] if len(tokens) > 1 else ""

    # Positional project when flags not used:
    #   /spec apply <id> <project>
    #   /spec mode <id> <mode> <project>
    #   /spec init <project>
    # create/propose/fill: project vs free-text request resolved separately
    # (quoted description must not become project).
    if sub in ("propose", "new", "create", "fill"):
        primary, project, request = _resolve_create_fill_args(
            tokens, project, request
        )
        secondary = ""
    elif not project:
        if sub == "mode" and len(tokens) >= 3:
            project = tokens[2]
        elif sub in (
            "apply",
            "run",
            "archive",
            "status",
            "show",
            "view",
        ) and len(tokens) >= 2:
            project = tokens[1]
        elif sub == "init" and tokens:
            project = tokens[0]
            primary = ""
            secondary = ""

    store = _store(host, project or None)
    proj_label = project or "."
    ws = _workspace(host)

    if sub in ("", "status", "list") and not primary:
        projects = discover_sdd_projects(ws)
        if not projects and not store.is_initialized():
            await _write(
                host,
                "SDD not initialized. Run `/spec init` or `/spec init <project-path>` "
                "or ask the agent to call sdd_init.\n"
                f"Workspace: `{ws}`",
            )
            return
        lines = ["**SDD status**", f"workspace: `{ws}`"]
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
        lines.append(_usage())
        await _write(host, "\n".join(lines))
        return

    if sub == "init":
        try:
            result = store.init()
            await _write(host, f"SDD init ({proj_label}): {result}\nworkspace: `{ws}`")
        except Exception as exc:
            await _write(host, f"Error: {exc}")
        return

    if sub in ("propose", "new", "create"):
        change_id = primary
        if not change_id:
            await _write(
                host,
                "Usage: `/spec create <change-id> [project] [\"request\" | -- request]`\n"
                "e.g. `/spec create company \"Add company section with groups\"`\n"
                "e.g. `/spec create oauth-login apps/web -- add OAuth login`",
            )
            return
        if not store.is_initialized():
            store.init()
        domain = "example"
        specs = store.list_specs()
        if specs:
            domain = specs[0]["domain"]
        try:
            prefs = _sdd_prefs(host)
            gate_on = bool(prefs.understanding_gate_enabled)
            thr = int(prefs.understanding_threshold)
            created = store.create_change(
                change_id,
                domain=domain,
                request=request or "",
                understanding_gate_enabled=gate_on,
                understanding_threshold=thr,
            )
            # Gate ON: keep clarifying — do not unlock to 100% on create.
            apply_hint = (
                f"`/spec apply {change_id} {project}`"
                if project
                else f"`/spec apply {change_id}`"
            )
            show_hint = (
                f"`/spec show {change_id} {project}`"
                if project
                else f"`/spec show {change_id}`"
            )
            fill_hint = (
                f"`/spec fill {change_id} {project}`"
                if project
                else f"`/spec fill {change_id}`"
            )
            req_note = f"\nRequest: {request[:200]}{'…' if len(request) > 200 else ''}" if request else ""
            und = created.get("understanding") or {}
            if gate_on and und.get("status") == "clarifying":
                await _write(
                    host,
                    f"Created change `{created['change_id']}` at `{created['path']}` "
                    f"(project `{proj_label}`).{req_note}\n"
                    f"Understanding gate ON (0% → {thr}%): agent will research and ask "
                    f"clarifying questions. View: {show_hint}\n"
                    f"After confirm, fill with {fill_hint} or let the agent continue.",
                )
                await _write(host, "Starting understanding / clarification agent…")
                await _dispatch_agent(
                    host,
                    _understanding_prompt(
                        change_id=change_id,
                        project=project,
                        request=request or "",
                        threshold=thr,
                    ),
                )
            else:
                await _write(
                    host,
                    f"Created change `{created['change_id']}` at `{created['path']}` "
                    f"(project `{proj_label}`).{req_note}\n"
                    f"View: {show_hint}\n"
                    f"Fill proposal/specs/tasks (with assignees), then {apply_hint}.",
                )
                if request:
                    await _write(host, "Starting agent to fill SDD artifacts…")
                    await _dispatch_agent(
                        host,
                        _fill_prompt(
                            change_id=change_id,
                            project=project,
                            request=request,
                        ),
                    )
        except FileExistsError:
            await _write(host, f"Change already exists: {change_id}")
        except Exception as exc:
            await _write(host, f"Error: {exc}")
        return

    if sub == "fill":
        change_id = primary
        if not change_id:
            await _write(
                host,
                "Usage: `/spec fill <change-id> [project] [-- request text]`",
            )
            return
        try:
            store.change_status(change_id)
        except FileNotFoundError:
            await _write(host, f"Change not found: {change_id} (project `{proj_label}`)")
            return
        except Exception as exc:
            await _write(host, f"Error: {exc}")
            return
        # User asked to fill — unlock gate so agent can write real tasks.
        fill_req = request
        if not fill_req:
            req_path = store.project_root / "openspec" / "changes" / change_id / "request.md"
            if not req_path.is_file():
                # change may live under workspace relative project
                from core.sdd.paths import change_dir

                cdir = change_dir(store.workspace, change_id)
                req_path = cdir / "request.md"
            try:
                fill_req = req_path.read_text(encoding="utf-8") if req_path.is_file() else ""
            except OSError:
                fill_req = ""
        _unlock_understanding_for_fill(store, change_id, request=fill_req)
        await _write(host, f"Filling change `{change_id}` via agent…")
        await _dispatch_agent(
            host,
            _fill_prompt(change_id=change_id, project=project, request=fill_req),
        )
        return

    if sub in ("show", "view") or (sub == "status" and primary):
        change_id = primary
        if not change_id:
            await _write(host, "Usage: `/spec show <change-id> [project]`")
            return
        try:
            from core.sdd.paths import change_dir

            st = store.change_status(change_id)
            data = st.to_dict()
            cdir = change_dir(store.workspace, change_id)
            lines = [
                f"**Change `{change_id}`** (project `{proj_label}`)",
                f"```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```",
                "",
                "**proposal.md**",
                "```",
                _preview_file(cdir / "proposal.md"),
                "```",
                "",
                "**tasks.md**",
                "```",
                _preview_file(cdir / "tasks.md"),
                "```",
            ]
            await _write(host, "\n".join(lines))
        except Exception as exc:
            await _write(host, f"Error: {exc}")
        return

    if sub == "mode":
        # /spec mode <id> <self|subagents|hybrid> [project]
        change_id = primary
        mode = secondary
        if not change_id or not mode:
            await _write(
                host,
                "Usage: `/spec mode <change-id> self|subagents|hybrid [project]`",
            )
            return
        try:
            result = store.set_apply_mode(change_id, mode)
            await _write(host, f"Apply mode set ({proj_label}): {result}")
        except Exception as exc:
            await _write(host, f"Error: {exc}")
        return

    if sub in ("apply", "run"):
        change_id = primary
        if not change_id:
            await _write(host, "Usage: `/spec apply <change-id> [project]`")
            return
        try:
            st = store.change_status(change_id)
            if not st.apply_mode:
                req = store.request_apply_mode(change_id)
                await _write(host, req.get("prompt") or "Choose apply mode first.")
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
                await _write(host, f"Then: {mode_cmd} and re-run {apply_cmd}.")
                return
            plan = store.begin_apply(change_id)
            if not plan.get("ok"):
                missing = plan.get("missing") or []
                err = plan.get("error") or "not ready"
                extra = f" Missing: {', '.join(missing)}." if missing else ""
                await _write(host, f"Cannot apply: {err}.{extra}")
                return
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
            await _write(host, "\n".join(lines))
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
                        await _write(
                            host,
                            "Auto-dispatched by tasks.md assignee:\n"
                            + "\n".join(
                                f"- task {j.get('task_id')} → job `{j.get('job_id')}` "
                                f"(type={j.get('executor')})"
                                for j in spawned
                            ),
                        )
                    if disp.get("errors"):
                        await _write(
                            host, "Dispatch errors: " + "; ".join(disp["errors"])
                        )
                except Exception as exc:
                    await _write(host, f"Auto-dispatch skipped: {exc}")
            await _dispatch_agent(
                host,
                _apply_agent_message(
                    change_id=change_id,
                    project=project,
                    apply_mode=str(plan.get("apply_mode") or ""),
                ),
            )
        except FileNotFoundError as exc:
            await _write(
                host,
                f"Change not found in project `{proj_label}`: {exc}. "
                "Pass the project path: `/spec apply <id> <project-path>`.",
            )
        except Exception as exc:
            await _write(host, f"Error: {exc}")
        return

    if sub == "archive":
        change_id = primary
        if not change_id:
            await _write(host, "Usage: `/spec archive <change-id> [project]`")
            return
        try:
            result = store.archive(change_id)
            await _write(host, f"Archived ({proj_label}): {result}")
        except Exception as exc:
            await _write(host, f"Error: {exc}")
        return

    await _write(host, _usage())
