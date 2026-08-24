# Code mode

Opt-in tool presentation: the model writes a **Python program** that calls Holix tools, instead of one JSON tool call per ReAct step.

Default is **native** function calling. Leave Telegram `main` on `native` until you opt a coder slot in.

Config keys belong in [CONFIGURATION.md](CONFIGURATION.md#code-mode-opt-in). Messenger menus belong in [SUBAGENTS.md](SUBAGENTS.md#telegram-and-max). This page is the behaviour of `run_code`.

## When to use

| Mode | Wire | Typical use |
|------|------|-------------|
| `native` | Usual tool schemas | Default. Chat, Telegram `main`. |
| `code` | Only `run_code` + SDK in the system prompt | Multi-file coding, many reads in one step. |
| `both` | Native schemas **and** `run_code` | Experiments; larger prompt. |

## Enable

`~/.holix/profiles/<name>/config.yaml`:

```yaml
tools_presentation: code   # native | code | both
```

Per-slot (Telegram `main` stays native, `coder` uses code):

```yaml
tools_presentation: native
tools_presentation_by_slot:
  coder: code
```

Optional caps:

```yaml
code_mode_wall_timeout_s: 120
code_mode_max_inner_calls: 40
code_mode_parallel_readonly: true
```

TUI and Telegram/MAX can switch the same keys without editing YAML — see [SUBAGENTS.md](SUBAGENTS.md#telegram-and-max).

## What the model writes

```python
hits = tools.grep(pattern="TODO", path=".")
return {"n": len(hits)}
```

- `tools` is already in scope. `import tools` / `from tools import …` alias the same object.
- `run_code` requires `code` (function body) and `description`.
- Only `print()` and `return` come back. Inner dumps are truncated and stay out of history.
- Relative paths and `run_terminal_command` start in profile `workspace_root` (shown in the SDK), not process CWD.
- Persistent servers: `tools.start_background_process(...)`, not `run_terminal_command`.
- Edit existing files with `tools.patch_file(path=..., old_string=..., new_string=...)`. `write_file` is for new files or a full rewrite.
- Probe localhost with `curl` via `run_terminal_command`. Browser `fetch_url` rejects localhost.
- Do not `import os`, `subprocess`, `pathlib`. File and shell work goes through `tools.*`.

## Safety

The program runs in an isolated **subprocess** (`python -I`), same idea as `execute_python`. Each `tools.name(...)` still goes through `ToolRegistry`: ActionGuard, workspace jail, allow-lists. Mutating tools still ask for confirmation.

Forbidden inside a program: `run_code`, `execute_python`, `ask_user`, `external_cli`, `delegate_to_subagent`, cron, browser tools. `todo_write` is allowed.

TUI and Telegram/MAX show a **collapsed card**: `description` plus inner tool names — not the program body.

## Limits (v1)

- Mutating inner calls run one at a time. Read-only tools (`risk_level: no`) may use `tools.parallel(...)`.
- Wall timeout (default 120s) and a cap on inner calls (default 40).
- Fresh worker every time (not a REPL).
- `>/dev/null` redirects are allowed; `/dev/tcp` and raw disks are not.
